from flask import Flask, render_template, send_file, request
import requests
import base64
from datetime import datetime, timedelta, time
from collections import defaultdict
import math
import statistics
from dotenv import load_dotenv
import os
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import io
from zoneinfo import ZoneInfo
import time as time_module

load_dotenv()


# --- CONFIGURACIÓN ---
#prueba de git

ORG_URL = "https://dev.azure.com/Grupo-Disbyte"
PROJECT_NAME = "Disbyte Infrastructure"
PAT = os.getenv("PAT")
USERS_TO_QUERY = ["Stefano Sanchez", "Geleser Pimentel"]
START_DATE = f"{datetime.now().year}-01-01"
API_VERSION_WIQL = "7.1-preview.2"
API_VERSION_BATCH = "7.1-preview.1"
meses_es = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
            "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
# Configuración de horario laboral
TIMEZONE = os.getenv("TIMEZONE", "UTC")
WORK_START_HOUR = 8
WORK_END_HOUR = 19
BUSINESS_DAYS = {0, 1, 2, 3, 4}  # 0 = Lunes ... 6 = Domingo

# === CACÉ TTL para llamadas a Azure DevOps ===
_api_cache = {}
CACHE_TTL_SECONDS = 300  # 5 minutos

def _get_cached_tickets(users_tuple, start_date, end_date=None):
    """Wrapper con caché TTL para get_done_tickets_by_month."""
    key = (users_tuple, start_date, end_date)
    now = time_module.time()
    if key in _api_cache and now - _api_cache[key]['ts'] < CACHE_TTL_SECONDS:
        print(f"⚡ Cache hit para {users_tuple}")
        return _api_cache[key]['data']
    data = get_done_tickets_by_month(list(users_tuple), start_date, end_date)
    _api_cache[key] = {'data': data, 'ts': now}
    return data

def _get_cached_near_sla():
    """Wrapper con caché TTL para get_active_tickets_near_sla."""
    key = 'near_sla'
    now = time_module.time()
    if key in _api_cache and now - _api_cache[key]['ts'] < CACHE_TTL_SECONDS:
        print(f"⚡ Cache hit near_sla")
        return _api_cache[key]['data']
    data = get_active_tickets_near_sla()
    _api_cache[key] = {'data': data, 'ts': now}
    return data

# --- LÓGICA DE DATOS ---
def get_done_tickets_by_month(user_list, start_date=None, end_date=None):
    if start_date is None:
        start_date = START_DATE
    
    # Ajuste de fechas para WIQL (solo fecha, sin hora, como pide la API para StateChangeDate)
    # Para incluir todo el día de end_date, usamos < (end_date + 1 día)
    date_condition = f"[Microsoft.VSTS.Common.StateChangeDate] >= '{start_date}'"
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            next_day_dt = end_dt + timedelta(days=1)
            next_day_str = next_day_dt.strftime("%Y-%m-%d")
            date_condition += f" AND [Microsoft.VSTS.Common.StateChangeDate] < '{next_day_str}'"
        except ValueError:
            # Fallback por si el formato no es YYYY-MM-DD
            date_condition += f" AND [Microsoft.VSTS.Common.StateChangeDate] <= '{end_date}'"

    try:
        assigned_to_conditions = [f"[System.AssignedTo] = '{user}'" for user in user_list]
        assigned_to_clause = " OR ".join(assigned_to_conditions)
        wiql_url = f"{ORG_URL}/{PROJECT_NAME}/_apis/wit/wiql?api-version={API_VERSION_WIQL}"
        query = {"query": f"""
                SELECT [System.Id] FROM workitems WHERE [System.TeamProject] = @project
                AND [System.WorkItemType] = 'Issue' AND [System.State] = 'Done'
                AND {date_condition} AND ({assigned_to_clause})
                ORDER BY [Microsoft.VSTS.Common.StateChangeDate] DESC """}
        authorization = str(base64.b64encode(bytes(':' + PAT, 'ascii')), 'ascii')
        headers = {'Content-Type': 'application/json', 'Authorization': 'Basic ' + authorization}
        print(f"🛰️  Buscando 'Issues' para: {', '.join(user_list)} (a partir de {start_date})...")
        response = requests.post(url=wiql_url, headers=headers, json=query)
        response.raise_for_status()
        work_items = response.json().get("workItems", [])
        if not work_items: return {}, [], {}, {}, {}, {}, {}, {}, {}
        ticket_ids = [item['id'] for item in work_items]
        print(f"✅ Se encontraron {len(ticket_ids)} 'Issues' que cumplen los criterios.")
        fields_to_request = ["System.CreatedDate", "Microsoft.VSTS.Common.StateChangeDate", "Microsoft.VSTS.Common.Priority", "System.Title"]
        batch_url = f"{ORG_URL}/_apis/wit/workitemsbatch?api-version={API_VERSION_BATCH}"
        all_detailed_tickets, chunk_size = [], 200
        for i in range(0, len(ticket_ids), chunk_size):
            chunk = ticket_ids[i:i + chunk_size]
            print(f"🔎 Procesando lote {math.ceil((i+1)/chunk_size)} de {math.ceil(len(ticket_ids)/chunk_size)}...")
            batch_payload = {"ids": chunk, "fields": fields_to_request}
            batch_response = requests.post(url=batch_url, headers=headers, json=batch_payload)
            batch_response.raise_for_status()
            all_detailed_tickets.extend(batch_response.json().get("value", []))
        print("📊 Agrupando resultados y calculando duraciones...")
        monthly_counts, ticket_details, monthly_durations = defaultdict(int), [], defaultdict(list)
        monthly_ticket_details = defaultdict(list)
        priority_counts, priority_durations = defaultdict(int), defaultdict(list)
        priority_ticket_details = defaultdict(list)
        monthly_priority_counts, monthly_priority_durations = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(list))
        for ticket in all_detailed_tickets:
            creation_date = datetime.fromisoformat(ticket['fields']['System.CreatedDate'].replace('Z', '+00:00'))
            completion_date = datetime.fromisoformat(ticket['fields']['Microsoft.VSTS.Common.StateChangeDate'].replace('Z', '+00:00'))
            duration = business_time_between(creation_date, completion_date)
            # Prioridad (1..4)
            priority_value = ticket['fields'].get('Microsoft.VSTS.Common.Priority')
            # Título del issue
            title = ticket['fields'].get('System.Title', 'Sin título')
            if isinstance(priority_value, int) and 1 <= priority_value <= 4:
                priority_counts[priority_value] += 1
                priority_durations[priority_value].append(duration)
                priority_ticket_details[priority_value].append({'id': ticket['id'], 'duration': duration, 'priority': priority_value, 'title': title})
            month_key = f"{meses_es[completion_date.month - 1]} {completion_date.year}"
            ticket_details.append({'id': ticket['id'], 'duration': duration, 'priority': priority_value, 'title': title})
            monthly_counts[month_key] += 1
            monthly_durations[month_key].append(duration)
            monthly_ticket_details[month_key].append({'id': ticket['id'], 'duration': duration, 'priority': priority_value, 'title': title})
            
            # Datos de prioridad por mes
            if isinstance(priority_value, int) and 1 <= priority_value <= 4:
                monthly_priority_counts[month_key][priority_value] += 1
                monthly_priority_durations[month_key][priority_value].append(duration)
        return monthly_counts, ticket_details, monthly_durations, monthly_ticket_details, priority_counts, priority_durations, priority_ticket_details, monthly_priority_counts, monthly_priority_durations
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}, [], {}, {}, {}, {}, {}, {}, {}

def format_timedelta(td):
    if not isinstance(td, timedelta) or td.total_seconds() <= 0: return "0"
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    if not parts: return "< 1m"
    return " ".join(parts)

def business_time_between(start_dt: datetime, end_dt: datetime) -> timedelta:
    """Calcula el tiempo transcurrido solo dentro del horario laboral definido.

    Considera días hábiles (lunes a viernes) y horas entre WORK_START_HOUR y WORK_END_HOUR
    en la zona horaria TIMEZONE. Excluye fines de semana y tiempo fuera de ese rango.
    """
    try:
        if not start_dt or not end_dt or end_dt <= start_dt:
            return timedelta(0)
        tz = ZoneInfo(TIMEZONE)
        start_local = start_dt.astimezone(tz)
        end_local = end_dt.astimezone(tz)
        total = timedelta(0)
        current_date = start_local.date()
        end_date = end_local.date()
        while current_date <= end_date:
            if current_date.weekday() in BUSINESS_DAYS:
                day_start = datetime.combine(current_date, time(WORK_START_HOUR, 0, 0), tzinfo=tz)
                day_end = datetime.combine(current_date, time(WORK_END_HOUR, 0, 0), tzinfo=tz)
                interval_start = max(start_local, day_start)
                interval_end = min(end_local, day_end)
                if interval_end > interval_start:
                    total += interval_end - interval_start
            current_date += timedelta(days=1)
        return total
    except Exception:
        return timedelta(0)

def generate_pdf_report(reports_data):
    """Genera un reporte PDF con los datos de métricas"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    
    # Estilos mejorados
    styles = getSampleStyleSheet()
    
    # Título principal más grande y elegante
    title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica-Bold'
    )
    
    # Subtítulo
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=8,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica'
    )
    
    # Títulos de sección
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=6,
        spaceBefore=8,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica-Bold',
        borderWidth=0,
        borderColor=colors.HexColor('#012f60'),
        borderPadding=3
    )
    
    # Estilo para texto normal
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=6,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica'
    )
    
    # Contenido del PDF
    story = []
    
    # PÁGINA 1: Título y primer reporte individual
    # Agregar logo de la empresa arriba del título
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'Logo.png')
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=0.8*inch, height=0.4*inch)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 10))
    except Exception as e:
        print(f"No se pudo cargar el logo: {e}")
    
    # Título principal más grande
    story.append(Paragraph("DASHBOARD DE MÉTRICAS DE SOPORTE IT", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Reportes generados para 'Issues' creados desde el {START_DATE}", subtitle_style))
    story.append(Spacer(1, 6))
    
    # Procesar solo el primer reporte (Geleser Pimentel)
    if len(reports_data) > 0:
        report = reports_data[0]
        # Formatear el título del reporte
        title_parts = report["title"].split(": ")
        if len(title_parts) > 1:
            report_type = title_parts[0].lower()  # "reporte individual" o "reporte combinado"
            user_name = title_parts[1].upper()    # Nombre en mayúsculas
            # Capitalizar la primera letra del tipo de reporte
            if report_type == "reporte individual":
                report_type = "Reporte individual"
            elif report_type == "reporte combinado":
                report_type = "Reporte combinado"
            elif report_type == "reporte anual":
                report_type = "Reporte Anual"
            formatted_title = f"{report_type}: {user_name}"
        else:
            formatted_title = report["title"]
        
        # Título del reporte con estilo mejorado
        story.append(Paragraph(formatted_title, section_style))
        
        if report["has_data"]:
            # Desglose mensual
            story.append(Paragraph("DESGLOSE MENSUAL", section_style))
            
            # Tabla mejorada para el desglose mensual
            monthly_data = [["MES", "CANTIDAD", "PROMEDIO"]]
            for item in report["monthly_breakdown"]:
                monthly_data.append([
                    item["month"],
                    str(item["count"]),
                    format_timedelta(item["median_duration"])
                ])
            
            monthly_table = Table(monthly_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
            monthly_table.setStyle(TableStyle([
                # Encabezado
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                # Filas de datos
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                # Bordes
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(monthly_table)
            story.append(Spacer(1, 6))
            
            # Métricas generales con diseño mejorado
            story.append(Paragraph("MÉTRICAS GENERALES", section_style))
            
            # Crear tabla para métricas generales
            general_metrics_data = [
                ["MÉTRICA", "VALOR"],
                ["Promedio mensual", format_timedelta(report['avg_duration'])]
            ]
            #comentario de prueba
            # Agregar desglose por prioridad
            if report.get('priority_breakdown'):
                for item in report['priority_breakdown']:
                    general_metrics_data.append([
                        f"Prioridad {item['priority']}",
                        f"{item['count']} tickets (promedio: {format_timedelta(item['avg_duration'])})"
                    ])
            general_metrics_table = Table(general_metrics_data, colWidths=[2.5*inch, 2.5*inch])
            general_metrics_table.setStyle(TableStyle([
                # Encabezado
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                # Filas de datos
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                # Bordes
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60'))
            ]))
            story.append(general_metrics_table)
        else:
            story.append(Paragraph("No se encontraron 'Issues' que cumplan los criterios.", normal_style))
    
    story.append(PageBreak())
    
    # PÁGINA 2: Segundo reporte individual (Stefano Sanchez)
    if len(reports_data) > 1:
        report = reports_data[1]
        # Formatear el título del reporte
        title_parts = report["title"].split(": ")
        if len(title_parts) > 1:
            report_type = title_parts[0].lower()
            user_name = title_parts[1].upper()
            # Capitalizar la primera letra del tipo de reporte
            if report_type == "reporte individual":
                report_type = "Reporte individual"
            elif report_type == "reporte combinado":
                report_type = "Reporte combinado"
            elif report_type == "reporte anual":
                report_type = "Reporte Anual"
            formatted_title = f"{report_type}: {user_name}"
        else:
            formatted_title = report["title"]
        
        story.append(Paragraph(formatted_title, section_style))
        
        if report["has_data"]:
            # Desglose mensual
            story.append(Paragraph("DESGLOSE MENSUAL", section_style))
            
            monthly_data = [["MES", "CANTIDAD", "PROMEDIO"]]
            for item in report["monthly_breakdown"]:
                monthly_data.append([
                    item["month"],
                    str(item["count"]),
                    format_timedelta(item["median_duration"])
                ])
            
            monthly_table = Table(monthly_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
            monthly_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(monthly_table)
            story.append(Spacer(1, 6))
            
            # Métricas generales
            story.append(Paragraph("MÉTRICAS GENERALES", section_style))
            
            general_metrics_data = [
                ["MÉTRICA", "VALOR"],
                ["Promedio mensual", format_timedelta(report['avg_duration'])]
            ]
            # Agregar desglose por prioridad
            if report.get('priority_breakdown'):
                for item in report['priority_breakdown']:
                    general_metrics_data.append([
                        f"Prioridad {item['priority']}",
                        f"{item['count']} tickets (promedio: {format_timedelta(item['avg_duration'])})"
                    ])
            
            general_metrics_table = Table(general_metrics_data, colWidths=[2.5*inch, 2.5*inch])
            general_metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60'))
            ]))
            story.append(general_metrics_table)
        else:
            story.append(Paragraph("No se encontraron 'Issues' que cumplan los criterios.", normal_style))
    
    story.append(PageBreak())
    
    # PÁGINA 3: Reporte combinado
    if len(reports_data) > 2:
        report = reports_data[2]
        # Formatear el título del reporte
        title_parts = report["title"].split(": ")
        if len(title_parts) > 1:
            report_type = title_parts[0].lower()
            user_name = title_parts[1].upper()
            # Capitalizar la primera letra del tipo de reporte
            if report_type == "reporte individual":
                report_type = "Reporte individual"
            elif report_type == "reporte combinado":
                report_type = "Reporte combinado"
            elif report_type == "reporte anual":
                report_type = "Reporte Anual"
            formatted_title = f"{report_type}: {user_name}"
        else:
            formatted_title = report["title"]
        
        story.append(Paragraph(formatted_title, section_style))
        
        if report["has_data"]:
            # Desglose mensual
            story.append(Paragraph("DESGLOSE MENSUAL", section_style))
            
            monthly_data = [["MES", "CANTIDAD", "PROMEDIO"]]
            for item in report["monthly_breakdown"]:
                monthly_data.append([
                    item["month"],
                    str(item["count"]),
                    format_timedelta(item["median_duration"])
                ])
            
            monthly_table = Table(monthly_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
            monthly_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(monthly_table)
            story.append(Spacer(1, 6))
            
            # Métricas generales
            story.append(Paragraph("MÉTRICAS GENERALES", section_style))
            
            general_metrics_data = [
                ["MÉTRICA", "VALOR"],
                ["Promedio mensual", format_timedelta(report['avg_duration'])]
            ]
            # Agregar desglose por prioridad
            if report.get('priority_breakdown'):
                for item in report['priority_breakdown']:
                    general_metrics_data.append([
                        f"Prioridad {item['priority']}",
                        f"{item['count']} tickets (promedio: {format_timedelta(item['avg_duration'])})"
                    ])
            
            general_metrics_table = Table(general_metrics_data, colWidths=[2.5*inch, 2.5*inch])
            general_metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60'))
            ]))
            story.append(general_metrics_table)
        else:
            story.append(Paragraph("No se encontraron 'Issues' que cumplan los criterios.", normal_style))
    
    # Pie de página profesional
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica'
    )
    
    # Agregar pie de página en la última página
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    footer_text = f"Reporte generado el {current_date} | Dashboard de Métricas de Soporte IT"
    story.append(Spacer(1, 20))
    story.append(Paragraph(footer_text, footer_style))
    
    # Generar el PDF
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- APLICACIÓN FLASK ---
app = Flask(__name__)

@app.route('/')
def dashboard():
    print("Generando reportes para la web...")
    reports_data = []
    
    report_definitions = [
        {"title": "REPORTE INDIVIDUAL: Geleser Pimentel", "users": ["Geleser Pimentel"]},
        {"title": "REPORTE INDIVIDUAL: Stefano Sanchez", "users": ["Stefano Sanchez"]},
        {"title": "REPORTE COMBINADO", "users": USERS_TO_QUERY}
    ]

    # 1. Obtener datos individuales (con caché)
    individual_results = {}
    for definition in report_definitions[:2]:  # Solo los individuales
        key = tuple(definition["users"])
        individual_results[key] = _get_cached_tickets(
            key, START_DATE
        )

    for definition in report_definitions:
        users_key = tuple(definition["users"])

        if definition["title"] == "REPORTE COMBINADO":
            # Combinar los datos ya obtenidos sin nueva llamada a la API
            r0 = individual_results.get(tuple(report_definitions[0]["users"]), ({}, [], {}, {}, {}, {}, {}, {}, {}))
            r1 = individual_results.get(tuple(report_definitions[1]["users"]), ({}, [], {}, {}, {}, {}, {}, {}, {}))
            results = dict(r0[0])
            for k, v in r1[0].items():
                results[k] = results.get(k, 0) + v
            details = r0[1] + r1[1]
            monthly_durations = {**r0[2]}
            for k, v in r1[2].items():
                monthly_durations[k] = monthly_durations.get(k, []) + v
            monthly_ticket_details = {**r0[3]}
            for k, v in r1[3].items():
                monthly_ticket_details[k] = monthly_ticket_details.get(k, []) + v
            priority_counts = dict(r0[4])
            for k, v in r1[4].items():
                priority_counts[k] = priority_counts.get(k, 0) + v
            priority_durations = {**r0[5]}
            for k, v in r1[5].items():
                priority_durations[k] = priority_durations.get(k, []) + v
            priority_ticket_details = {**r0[6]}
            for k, v in r1[6].items():
                priority_ticket_details[k] = priority_ticket_details.get(k, []) + v
            monthly_priority_counts = dict(r0[7])
            for k, v in r1[7].items():
                for p, c in v.items():
                    monthly_priority_counts.setdefault(k, {}).setdefault(p, 0)
                    monthly_priority_counts[k][p] += c
            monthly_priority_durations = dict(r0[8])
            for k, v in r1[8].items():
                for p, d in v.items():
                    monthly_priority_durations.setdefault(k, {}).setdefault(p, [])
                    monthly_priority_durations[k][p] += d
        else:
            results, details, monthly_durations, monthly_ticket_details, priority_counts, priority_durations, priority_ticket_details, monthly_priority_counts, monthly_priority_durations = individual_results[users_key]
        
        report = {"title": definition["title"], "has_data": False}
        
        if results:
            report["has_data"] = True
            
            # Pre-procesa todos los datos aquí, en Python
            monthly_breakdown = []
            sorted_months = sorted(results.items(), key=lambda item: (int(item[0].split(" ")[1]), meses_es.index(item[0].split(" ")[0])), reverse=True)
            
            # Procesar todos los meses del año actual primero (orden cronológico inverso)
            for month, count in sorted_months:
                month_data = {"month": month, "count": count, "is_previous_year": False}
                durations_this_month = monthly_durations.get(month, [])
                if durations_this_month:
                    month_data["avg_duration"] = sum(durations_this_month, timedelta()) / len(durations_this_month)
                    month_data["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations_this_month]))
                else:
                    month_data["avg_duration"] = None
                    month_data["median_duration"] = None
                monthly_breakdown.append(month_data)
            
            # Calcular el total de tickets
            total_tickets = sum(item["count"] for item in monthly_breakdown)
            report["total_tickets"] = total_tickets

            report["monthly_breakdown"] = monthly_breakdown
            report["monthly_details"] = monthly_ticket_details
            report["priority_details"] = priority_ticket_details

            if details:
                durations = [d['duration'] for d in details]
                # Calcular promedio de las medianas mensuales
                monthly_medians = []
                for month, count in sorted_months:
                    durations_this_month = monthly_durations.get(month, [])
                    if durations_this_month:
                        # Calcular la mediana de este mes
                        month_median = statistics.median([td.total_seconds() for td in durations_this_month])
                        monthly_medians.append(month_median)
                
                if monthly_medians:
                    avg_median_seconds = sum(monthly_medians) / len(monthly_medians)
                    report["avg_duration"] = timedelta(seconds=avg_median_seconds)
                else:
                    report["avg_duration"] = timedelta(0)
                
                report["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations]))
                report["top_issues"] = sorted(details, key=lambda x: x['duration'], reverse=True)[:5]
                
                # Desglose por prioridad
                priority_breakdown = []
                for p in [1, 2, 3, 4]:
                    count_p = priority_counts.get(p, 0)
                    durations_p = priority_durations.get(p, [])
                    avg_p = (sum(durations_p, timedelta()) / len(durations_p)) if durations_p else None
                    priority_breakdown.append({
                        'priority': p,
                        'count': count_p,
                        'avg_duration': avg_p
                    })
                report['priority_breakdown'] = priority_breakdown
                
                # Desglose por prioridad por mes
                monthly_priority_breakdown = {}
                for month in results.keys():
                    monthly_priority_breakdown[month] = []
                    for p in [1, 2, 3, 4]:
                        count_p = monthly_priority_counts.get(month, {}).get(p, 0)
                        durations_p = monthly_priority_durations.get(month, {}).get(p, [])
                        avg_p = (sum(durations_p, timedelta()) / len(durations_p)) if durations_p else None
                        monthly_priority_breakdown[month].append({
                            'priority': p,
                            'count': count_p,
                            'avg_duration': avg_p
                        })
                report['monthly_priority_breakdown'] = monthly_priority_breakdown
        
        reports_data.append(report)

    # Serializar para JavaScript (gráficos) — convertir timedeltas a segundos
    reports_data_js = []
    for r in reports_data:
        r_js = {'title': r['title'], 'has_data': r.get('has_data', False)}
        if r_js['has_data']:
            r_js['monthlyBreakdown'] = [
                {'month': m['month'], 'count': m['count']}
                for m in r.get('monthly_breakdown', [])
            ]
            r_js['priorityBreakdown'] = [
                {'priority': p['priority'], 'count': p['count']}
                for p in r.get('priority_breakdown', [])
            ]
        reports_data_js.append(r_js)

    near_sla_tickets = _get_cached_near_sla()

    # Pasamos la función format_timedelta al template para poder usarla
    return render_template('index.html',
                          reports=reports_data,
                          reports_js=reports_data_js,
                          format_timedelta=format_timedelta,
                          START_DATE=START_DATE,
                          get_sla_limit=get_sla_limit,
                          get_sla_warning_limit=get_sla_warning_limit,
                          near_sla_tickets=near_sla_tickets)


@app.route('/issue-details/<int:issue_id>')
def get_issue_details(issue_id):
    """Obtiene los detalles de un issue específico"""
    try:
        # URL para obtener detalles del work item
        work_item_url = f"{ORG_URL}/{PROJECT_NAME}/_apis/wit/workitems/{issue_id}?api-version=7.1-preview.3"
        
        # Autenticación
        authorization = str(base64.b64encode(bytes(':' + PAT, 'ascii')), 'ascii')
        headers = {'Authorization': 'Basic ' + authorization}
        
        print(f"🔍 Obteniendo detalles del Issue #{issue_id}...")
        response = requests.get(url=work_item_url, headers=headers)
        response.raise_for_status()
        
        work_item = response.json()
        fields = work_item.get('fields', {})
        
        # Extraer información relevante
        issue_details = {
            'id': issue_id,
            'title': fields.get('System.Title', 'Sin título'),
            'description': fields.get('System.Description', 'Sin descripción'),
            'created_date': fields.get('System.CreatedDate', ''),
            'state_change_date': fields.get('Microsoft.VSTS.Common.StateChangeDate', ''),
            'priority': fields.get('Microsoft.VSTS.Common.Priority', 'N/A'),
            'assigned_to': fields.get('System.AssignedTo', {}).get('displayName', 'Sin asignar') if isinstance(fields.get('System.AssignedTo'), dict) else 'Sin asignar',
            'state': fields.get('System.State', 'Desconocido')
        }
        
        # Obtener comentarios/discusión del issue
        try:
            comments_url = f"{ORG_URL}/{PROJECT_NAME}/_apis/wit/workItems/{issue_id}/comments?api-version=7.1-preview.3"
            comments_response = requests.get(url=comments_url, headers=headers)
            comments_response.raise_for_status()
            comments_data = comments_response.json()
            
            # Procesar comentarios
            comments = []
            if comments_data.get('comments'):
                for comment in comments_data['comments']:
                    comment_info = {
                        'id': comment.get('id'),
                        'text': comment.get('text', ''),
                        'created_date': comment.get('createdDate', ''),
                        'created_by': comment.get('createdBy', {}).get('displayName', 'Usuario desconocido') if isinstance(comment.get('createdBy'), dict) else 'Usuario desconocido'
                    }
                    
                    # Formatear fecha del comentario
                    if comment_info['created_date']:
                        try:
                            comment_dt = datetime.fromisoformat(comment_info['created_date'].replace('Z', '+00:00'))
                            comment_info['created_date_formatted'] = comment_dt.strftime('%d/%m/%Y %H:%M')
                        except:
                            comment_info['created_date_formatted'] = comment_info['created_date']
                    else:
                        comment_info['created_date_formatted'] = 'N/A'
                    
                    comments.append(comment_info)
            
            issue_details['comments'] = comments
            print(f"✅ Se encontraron {len(comments)} comentarios para el Issue #{issue_id}")
            
        except Exception as e:
            print(f"⚠️ No se pudieron obtener los comentarios del Issue #{issue_id}: {e}")
            issue_details['comments'] = []
        
        # Formatear fechas
        if issue_details['created_date']:
            try:
                created_dt = datetime.fromisoformat(issue_details['created_date'].replace('Z', '+00:00'))
                issue_details['created_date_formatted'] = created_dt.strftime('%d/%m/%Y %H:%M')
            except:
                issue_details['created_date_formatted'] = issue_details['created_date']
        else:
            issue_details['created_date_formatted'] = 'N/A'
            
        if issue_details['state_change_date']:
            try:
                state_change_dt = datetime.fromisoformat(issue_details['state_change_date'].replace('Z', '+00:00'))
                issue_details['state_change_date_formatted'] = state_change_dt.strftime('%d/%m/%Y %H:%M')
            except:
                issue_details['state_change_date_formatted'] = issue_details['state_change_date']
        else:
            issue_details['state_change_date_formatted'] = 'N/A'
        
        return issue_details
        
    except Exception as e:
        print(f"❌ Error obteniendo detalles del Issue #{issue_id}: {e}")
        return {
            'id': issue_id,
            'title': 'Error al cargar',
            'description': f'No se pudieron cargar los detalles del issue: {str(e)}',
            'created_date_formatted': 'N/A',
            'state_change_date_formatted': 'N/A',
            'priority': 'N/A',
            'assigned_to': 'N/A',
            'state': 'N/A',
            'comments': []
        }

@app.route('/export-pdf')
def export_pdf():
    """Exporta los reportes como PDF"""
    print("Generando reporte PDF...")
    reports_data = []
    
    report_definitions = [
        {"title": "REPORTE INDIVIDUAL: Geleser Pimentel", "users": ["Geleser Pimentel"]},
        {"title": "REPORTE INDIVIDUAL: Stefano Sanchez", "users": ["Stefano Sanchez"]},
        {"title": "REPORTE COMBINADO", "users": USERS_TO_QUERY}
    ]

    for definition in report_definitions:
        results, details, monthly_durations, monthly_ticket_details, priority_counts, priority_durations, priority_ticket_details, monthly_priority_counts, monthly_priority_durations = get_done_tickets_by_month(definition["users"])
        
        report = {"title": definition["title"], "has_data": False}
        
        if results:
            report["has_data"] = True
            
            # Pre-procesa todos los datos aquí, en Python
            monthly_breakdown = []
            sorted_months = sorted(results.items(), key=lambda item: (int(item[0].split(" ")[1]), meses_es.index(item[0].split(" ")[0])), reverse=True)
            
            for month, count in sorted_months:
                month_data = {"month": month, "count": count}
                durations_this_month = monthly_durations.get(month, [])
                if durations_this_month:
                    month_data["avg_duration"] = sum(durations_this_month, timedelta()) / len(durations_this_month)
                    month_data["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations_this_month]))
                else:
                    month_data["avg_duration"] = None
                    month_data["median_duration"] = None
                monthly_breakdown.append(month_data)

            # Calcular el total de tickets
            total_tickets = sum(item["count"] for item in monthly_breakdown)
            report["total_tickets"] = total_tickets

            report["monthly_breakdown"] = monthly_breakdown
            report["monthly_details"] = monthly_ticket_details
            report["priority_details"] = priority_ticket_details

            if details:
                durations = [d['duration'] for d in details]
                # Calcular promedio de las medianas mensuales
                monthly_medians = []
                for month, count in sorted_months:
                    durations_this_month = monthly_durations.get(month, [])
                    if durations_this_month:
                        # Calcular la mediana de este mes
                        month_median = statistics.median([td.total_seconds() for td in durations_this_month])
                        monthly_medians.append(month_median)
                
                if monthly_medians:
                    avg_median_seconds = sum(monthly_medians) / len(monthly_medians)
                    report["avg_duration"] = timedelta(seconds=avg_median_seconds)
                else:
                    report["avg_duration"] = timedelta(0)
                
                report["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations]))
                report["top_issues"] = sorted(details, key=lambda x: x['duration'], reverse=True)[:5]
                
                # Desglose por prioridad
                priority_breakdown = []
                for p in [1, 2, 3, 4]:
                    count_p = priority_counts.get(p, 0)
                    durations_p = priority_durations.get(p, [])
                    avg_p = (sum(durations_p, timedelta()) / len(durations_p)) if durations_p else None
                    priority_breakdown.append({
                        'priority': p,
                        'count': count_p,
                        'avg_duration': avg_p
                    })
                report['priority_breakdown'] = priority_breakdown
                
                # Desglose por prioridad por mes
                monthly_priority_breakdown = {}
                for month in results.keys():
                    monthly_priority_breakdown[month] = []
                    for p in [1, 2, 3, 4]:
                        count_p = monthly_priority_counts.get(month, {}).get(p, 0)
                        durations_p = monthly_priority_durations.get(month, {}).get(p, [])
                        avg_p = (sum(durations_p, timedelta()) / len(durations_p)) if durations_p else None
                        monthly_priority_breakdown[month].append({
                            'priority': p,
                            'count': count_p,
                            'avg_duration': avg_p
                        })
                report['monthly_priority_breakdown'] = monthly_priority_breakdown
        
        reports_data.append(report)
    
    # Generar el PDF
    pdf_buffer = generate_pdf_report(reports_data)
    
    # Generar nombre de archivo con fecha
    current_date = datetime.now().strftime("%Y-%m-%d")
    filename = f"reporte_metricas_soporte_{current_date}.pdf"
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

# --- FUNCIONES HELPER PARA SLA ---
def get_sla_limit(priority):
    """Calcula el límite de SLA en segundos según la prioridad"""
    sla_limits = {
        1: 4 * 3600,      # P1: 4 horas
        2: 8 * 3600,      # P2: 8 horas  
        3: 2 * 24 * 3600, # P3: 2 días hábiles (aproximado)
        4: 5 * 24 * 3600  # P4: 5 días hábiles (aproximado)
    }
    return sla_limits.get(priority, 2 * 24 * 3600)  # Default: 2 días

def get_sla_warning_limit(priority):
    """Calcula el límite de advertencia en segundos según la prioridad"""
    warning_limits = {
        1: 2 * 3600,      # P1: 2 horas (50% del límite)
        2: 4 * 3600,      # P2: 4 horas (50% del límite)
        3: 1 * 24 * 3600, # P3: 1 día hábil (50% del límite)
        4: 3 * 24 * 3600  # P4: 3 días hábiles (60% del límite)
    }
    return warning_limits.get(priority, 1 * 24 * 3600)  # Default: 1 día

def get_active_tickets_near_sla():
    """Obtiene tickets activos (no Done) que están próximos a vencer su SLA.
    Alerta P1/P2 cuando queda < 1 hora, P3/P4 cuando queda < 1 día."""
    try:
        wiql_url = f"{ORG_URL}/{PROJECT_NAME}/_apis/wit/wiql?api-version={API_VERSION_WIQL}"
        query = {"query": f"""
            SELECT [System.Id] FROM workitems
            WHERE [System.TeamProject] = @project
            AND [System.WorkItemType] = 'Issue'
            AND [System.State] IN ('To Do', 'Doing')
            ORDER BY [System.CreatedDate] ASC"""}
        authorization = str(base64.b64encode(bytes(':' + PAT, 'ascii')), 'ascii')
        headers = {'Content-Type': 'application/json', 'Authorization': 'Basic ' + authorization}
        print(f"🔍 Buscando todos los tickets activos próximos a vencer SLA...")
        response = requests.post(url=wiql_url, headers=headers, json=query)
        response.raise_for_status()
        work_items = response.json().get("workItems", [])
        if not work_items:
            return {}
        ticket_ids = [item['id'] for item in work_items]
        fields_to_request = ["System.CreatedDate", "Microsoft.VSTS.Common.Priority", "System.Title", "System.AssignedTo", "System.State"]
        batch_url = f"{ORG_URL}/_apis/wit/workitemsbatch?api-version={API_VERSION_BATCH}"
        all_tickets = []
        for i in range(0, len(ticket_ids), 200):
            chunk = ticket_ids[i:i + 200]
            batch_response = requests.post(url=batch_url, headers=headers, json={"ids": chunk, "fields": fields_to_request})
            batch_response.raise_for_status()
            all_tickets.extend(batch_response.json().get("value", []))

        now_dt = datetime.now(tz=ZoneInfo(TIMEZONE))
        near_expiry_by_priority = {}

        for ticket in all_tickets:
            priority_value = ticket['fields'].get('Microsoft.VSTS.Common.Priority')
            if not isinstance(priority_value, int) or priority_value not in [1, 2, 3, 4]:
                continue
            creation_date = datetime.fromisoformat(ticket['fields']['System.CreatedDate'].replace('Z', '+00:00'))
            title = ticket['fields'].get('System.Title', 'Sin título')
            state = ticket['fields'].get('System.State', '')
            assigned_raw = ticket['fields'].get('System.AssignedTo', '')
            if isinstance(assigned_raw, dict):
                assigned_to = assigned_raw.get('displayName', 'Sin asignar')
            else:
                assigned_to = str(assigned_raw) if assigned_raw else 'Sin asignar'

            elapsed = business_time_between(creation_date, now_dt)
            sla_limit_secs = get_sla_limit(priority_value)
            remaining_secs = sla_limit_secs - elapsed.total_seconds()

            # Umbrales de alerta: 1 hora para P1/P2, 1 día (24h) para P3/P4
            threshold = 3600 if priority_value in [1, 2] else 86400

            if remaining_secs <= threshold:
                is_expired = remaining_secs <= 0
                abs_td = timedelta(seconds=abs(remaining_secs))
                time_str = format_timedelta(abs_td)
                if is_expired:
                    remaining_display = f"Vencido hace {time_str}" if time_str != "0" else "Recién vencido"
                else:
                    remaining_display = f"Vence en {time_str}"

                near_expiry_by_priority.setdefault(priority_value, []).append({
                    'id': ticket['id'],
                    'title': title,
                    'state': state,
                    'assigned_to': assigned_to,
                    'remaining_display': remaining_display,
                    'is_expired': is_expired,
                    'remaining_secs': remaining_secs,
                })

        for p in near_expiry_by_priority:
            near_expiry_by_priority[p].sort(key=lambda x: x['remaining_secs'])

        total = sum(len(v) for v in near_expiry_by_priority.values())
        print(f"⚠️  Tickets próximos a vencer SLA: {total}")
        return near_expiry_by_priority
    except Exception as e:
        print(f"❌ Error obteniendo tickets near SLA: {e}")
        return {}


@app.route('/annual-report')
def annual_report():
    """Genera el reporte anual para el año seleccionado o el actual"""
    selected_year = request.args.get('year', default=datetime.now().year, type=int)
    annual_start_date = f"{selected_year}-01-01"
    annual_end_date = f"{selected_year}-12-31"
    print(f"Generando reporte anual para {selected_year} (desde {annual_start_date} hasta {annual_end_date})...")
    
    reports_data = []
    # Solo Geleser y Stefano para el reporte anual
    report_definitions = [
        {"title": f"REPORTE ANUAL {selected_year}: Geleser Pimentel", "users": ["Geleser Pimentel"]},
        {"title": f"REPORTE ANUAL {selected_year}: Stefano Sanchez", "users": ["Stefano Sanchez"]}
    ]

    for definition in report_definitions:
        results, details, monthly_durations, monthly_ticket_details, priority_counts, priority_durations, priority_ticket_details, monthly_priority_counts, monthly_priority_durations = get_done_tickets_by_month(definition["users"], start_date=annual_start_date, end_date=annual_end_date)
        
        report = {"title": definition["title"], "has_data": False}
        
        if results:
            report["has_data"] = True
            monthly_breakdown = []
            # Ordenar cronológicamente para el reporte anual (Enero -> Diciembre)
            sorted_months = sorted(results.items(), key=lambda item: (int(item[0].split(" ")[1]), meses_es.index(item[0].split(" ")[0])))
            
            for month, count in sorted_months:
                month_data = {"month": month, "count": count}
                durations_this_month = monthly_durations.get(month, [])
                if durations_this_month:
                    month_data["avg_duration"] = sum(durations_this_month, timedelta()) / len(durations_this_month)
                    month_data["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations_this_month]))
                else:
                    month_data["avg_duration"] = None
                    month_data["median_duration"] = None
                monthly_breakdown.append(month_data)

            report["total_tickets"] = sum(item["count"] for item in monthly_breakdown)
            report["monthly_breakdown"] = monthly_breakdown
            report["monthly_details"] = monthly_ticket_details
            
            # Métricas globales del año
            if details:
                durations = [d['duration'] for d in details]
                report["avg_duration"] = sum(durations, timedelta()) / len(durations) if durations else timedelta(0)
                report["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations]))
                
                # Desglose por prioridad
                priority_breakdown = []
                for p in [1, 2, 3, 4]:
                    count_p = priority_counts.get(p, 0)
                    durations_p = priority_durations.get(p, [])
                    avg_p = (sum(durations_p, timedelta()) / len(durations_p)) if durations_p else None
                    priority_breakdown.append({
                        'priority': p,
                        'count': count_p,
                        'avg_duration': avg_p
                    })
                report['priority_breakdown'] = priority_breakdown

        reports_data.append(report)

    # Calcular Grand Total (Suma de ambos)
    grand_total_tickets = 0
    grand_total_avg_duration = timedelta(0)
    total_duration_sum = timedelta(0)
    total_tickets_count = 0
    
    # Variables for Grand Total SLA
    grand_total_sla_met = 0
    grand_total_sla_tickets_count = 0

    for report in reports_data:
        if report.get("has_data"):
            grand_total_tickets += report.get("total_tickets", 0)
            # Para el promedio ponderado global
            if report.get("avg_duration") and report.get("total_tickets"):
                total_duration_sum += report["avg_duration"] * report["total_tickets"]
                total_tickets_count += report["total_tickets"]
            
            # Calcular SLA para cada reporte individual
            sla_met_count = 0
            total_sla_tickets = 0
            if report.get("monthly_details"):
                for month_tickets in report["monthly_details"].values():
                    for ticket in month_tickets:
                        total_sla_tickets += 1
                        sla_limit = get_sla_limit(ticket['priority'])
                        if ticket['duration'].total_seconds() <= sla_limit:
                            sla_met_count += 1
            
            report["sla_met_count"] = sla_met_count
            report["total_sla_tickets"] = total_sla_tickets
            sla_percentage = (sla_met_count / total_sla_tickets * 100) if total_sla_tickets > 0 else 0
            report["sla_percentage"] = sla_percentage
            
            # Determinar color del SLA
            if sla_percentage >= 70:
                report["sla_color"] = "#22c55e" # Green
            elif sla_percentage >= 60:
                report["sla_color"] = "#f59e0b" # Yellow
            else:
                report["sla_color"] = "#ef4444" # Red
                
            # Accumulate for Grand Total SLA
            grand_total_sla_met += sla_met_count
            grand_total_sla_tickets_count += total_sla_tickets

    if total_tickets_count > 0:
        grand_total_avg_duration = total_duration_sum / total_tickets_count
        
    # Calculate Grand Total SLA Percentage and Color
    grand_total_sla_percentage = (grand_total_sla_met / grand_total_sla_tickets_count * 100) if grand_total_sla_tickets_count > 0 else 0
    
    grand_total_sla_color = "#ef4444" # Default Red
    if grand_total_sla_percentage >= 70:
        grand_total_sla_color = "#22c55e" # Green
    elif grand_total_sla_percentage >= 60:
        grand_total_sla_color = "#f59e0b" # Yellow

    grand_total_data = {
        "total_tickets": grand_total_tickets,
        "avg_duration": grand_total_avg_duration,
        "sla_met_count": grand_total_sla_met,
        "total_sla_tickets": grand_total_sla_tickets_count,
        "sla_percentage": grand_total_sla_percentage,
        "sla_color": grand_total_sla_color
    }
    
    # Lista de años para el selector (desde 2025 hasta el año actual)
    available_years = list(range(2025, datetime.now().year + 1))

    # Crear versión serializable para JavaScript (gráficos)
    reports_data_js = []
    for r in reports_data:
        r_js = r.copy()
        if r_js.get("has_data"):
            # Convertir timedeltas en monthly_breakdown
            new_monthly = []
            for m in r_js["monthly_breakdown"]:
                m_copy = m.copy()
                # Usar 'is not None' para no saltear timedelta(0) que es falsy
                if m_copy.get("avg_duration") is not None and isinstance(m_copy["avg_duration"], timedelta):
                    m_copy["avg_duration"] = m_copy["avg_duration"].total_seconds()
                if "median_duration" in m_copy:
                    del m_copy["median_duration"]
                new_monthly.append(m_copy)
            r_js["monthly_breakdown"] = new_monthly

            # Convertir timedeltas en priority_breakdown
            if r_js.get("priority_breakdown"):
                new_priority = []
                for p in r_js["priority_breakdown"]:
                    p_copy = p.copy()
                    if p_copy.get("avg_duration") is not None and isinstance(p_copy["avg_duration"], timedelta):
                        p_copy["avg_duration"] = p_copy["avg_duration"].total_seconds()
                    new_priority.append(p_copy)
                r_js["priority_breakdown"] = new_priority

            # Convertir métricas globales
            if r_js.get("avg_duration") is not None and isinstance(r_js["avg_duration"], timedelta):
                r_js["avg_duration"] = r_js["avg_duration"].total_seconds()
            if "median_duration" in r_js:
                del r_js["median_duration"]

            # Eliminar cualquier objeto complejo que pueda tener timedeltas
            for key in ["monthly_details", "priority_details", "monthly_priority_breakdown"]:
                r_js.pop(key, None)

        reports_data_js.append(r_js)

    return render_template('annual_report.html', 
                          reports=reports_data, 
                          reports_js=reports_data_js,
                          grand_total=grand_total_data,
                          format_timedelta=format_timedelta, 
                          START_DATE=annual_start_date,
                          current_year=selected_year,
                          available_years=available_years)


@app.route('/annual-report-pdf')
def export_annual_pdf():
    """Exporta el reporte anual como PDF para el año seleccionado"""
    selected_year = request.args.get('year', default=datetime.now().year, type=int)
    annual_start_date = f"{selected_year}-01-01"
    annual_end_date = f"{selected_year}-12-31"
    print(f"Exportando PDF reporte anual para {selected_year}...")
    
    reports_data = []
    report_definitions = [
        {"title": f"REPORTE ANUAL {selected_year}: Geleser Pimentel", "users": ["Geleser Pimentel"]},
        {"title": f"REPORTE ANUAL {selected_year}: Stefano Sanchez", "users": ["Stefano Sanchez"]}
    ]

    for definition in report_definitions:
        results, details, monthly_durations, monthly_ticket_details, priority_counts, priority_durations, priority_ticket_details, monthly_priority_counts, monthly_priority_durations = get_done_tickets_by_month(definition["users"], start_date=annual_start_date, end_date=annual_end_date)
        
        report = {"title": definition["title"], "has_data": False}
        if results:
            report["has_data"] = True
            monthly_breakdown = []
            sorted_months = sorted(results.items(), key=lambda item: (int(item[0].split(" ")[1]), meses_es.index(item[0].split(" ")[0])))
            
            for month, count in sorted_months:
                month_data = {"month": month, "count": count}
                durations_this_month = monthly_durations.get(month, [])
                if durations_this_month:
                    month_data["avg_duration"] = sum(durations_this_month, timedelta()) / len(durations_this_month)
                    month_data["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations_this_month]))
                else:
                    month_data["avg_duration"] = None
                    month_data["median_duration"] = None
                monthly_breakdown.append(month_data)

            report["total_tickets"] = sum(item["count"] for item in monthly_breakdown)
            report["monthly_breakdown"] = monthly_breakdown
            
            if details:
                durations = [d['duration'] for d in details]
                report["avg_duration"] = sum(durations, timedelta()) / len(durations) if durations else timedelta(0)
                report["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations]))
                
                priority_breakdown = []
                for p in [1, 2, 3, 4]:
                    count_p = priority_counts.get(p, 0)
                    durations_p = priority_durations.get(p, [])
                    avg_p = (sum(durations_p, timedelta()) / len(durations_p)) if durations_p else None
                    priority_breakdown.append({'priority': p, 'count': count_p, 'avg_duration': avg_p})
                report['priority_breakdown'] = priority_breakdown

        reports_data.append(report)
    
    pdf_buffer = generate_pdf_report(reports_data)
    filename = f"reporte_anual_{selected_year}_soporte.pdf"
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
from flask import Flask, render_template, send_file
import requests
import base64
from datetime import datetime, timedelta
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

load_dotenv()
PAT = os.getenv("PAT")


# --- CONFIGURACIÓN ---
#prueba de git

ORG_URL = "https://dev.azure.com/Grupo-Disbyte"
PROJECT_NAME = "Disbyte Infrastructure"
PAT = os.getenv("PAT")   
USERS_TO_QUERY = ["Stefano Sanchez", "Geleser Pimentel"]
START_DATE = "2025-03-25"
API_VERSION_WIQL = "7.1-preview.2"
API_VERSION_BATCH = "7.1-preview.1"
meses_es = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
            "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

# --- LÓGICA DE DATOS ---
def get_done_tickets_by_month(user_list):
    try:
        assigned_to_conditions = [f"[System.AssignedTo] = '{user}'" for user in user_list]
        assigned_to_clause = " OR ".join(assigned_to_conditions)
        wiql_url = f"{ORG_URL}/{PROJECT_NAME}/_apis/wit/wiql?api-version={API_VERSION_WIQL}"
        query = {"query": f"""
                SELECT [System.Id] FROM workitems WHERE [System.TeamProject] = @project
                AND [System.WorkItemType] = 'Issue' AND [System.State] = 'Done'
                AND [System.CreatedDate] >= '{START_DATE}T00:00:00Z' AND ({assigned_to_clause})
                ORDER BY [Microsoft.VSTS.Common.StateChangeDate] DESC """}
        authorization = str(base64.b64encode(bytes(':' + PAT, 'ascii')), 'ascii')
        headers = {'Content-Type': 'application/json', 'Authorization': 'Basic ' + authorization}
        print(f"🛰️  Buscando 'Issues' para: {', '.join(user_list)} (a partir de {START_DATE})...")
        response = requests.post(url=wiql_url, headers=headers, json=query)
        response.raise_for_status()
        work_items = response.json().get("workItems", [])
        if not work_items: return {}, [], {}
        ticket_ids = [item['id'] for item in work_items]
        print(f"✅ Se encontraron {len(ticket_ids)} 'Issues' que cumplen los criterios.")
        fields_to_request = ["System.CreatedDate", "Microsoft.VSTS.Common.StateChangeDate"]
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
        for ticket in all_detailed_tickets:
            creation_date = datetime.fromisoformat(ticket['fields']['System.CreatedDate'].replace('Z', '+00:00'))
            completion_date = datetime.fromisoformat(ticket['fields']['Microsoft.VSTS.Common.StateChangeDate'].replace('Z', '+00:00'))
            duration = completion_date - creation_date
            ticket_details.append({'id': ticket['id'], 'duration': duration})
            month_key = f"{meses_es[completion_date.month - 1]} {completion_date.year}"
            monthly_counts[month_key] += 1
            monthly_durations[month_key].append(duration)
        return monthly_counts, ticket_details, monthly_durations
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None, None

def format_timedelta(td):
    if not isinstance(td, timedelta) or td.total_seconds() <= 0: return "N/A"
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    if not parts: return "< 1m"
    return " ".join(parts)

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
        fontSize=20,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica-Bold'
    )
    
    # Subtítulo
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica'
    )
    
    # Títulos de sección
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=13,
        spaceAfter=8,
        spaceBefore=12,
        textColor=colors.HexColor('#012f60'),
        fontName='Helvetica-Bold',
        borderWidth=0,
        borderColor=colors.HexColor('#012f60'),
        borderPadding=5
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
            logo = Image(logo_path, width=1*inch, height=0.5*inch)
            logo.hAlign = 'CENTER'
            story.append(logo)
            story.append(Spacer(1, 15))
    except Exception as e:
        print(f"No se pudo cargar el logo: {e}")
    
    # Título principal más grande
    story.append(Paragraph("DASHBOARD DE MÉTRICAS DE SOPORTE IT", title_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Reportes generados para 'Issues' creados desde el {START_DATE}", subtitle_style))
    story.append(Spacer(1, 10))
    
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
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                # Filas de datos
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                # Bordes
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(monthly_table)
            story.append(Spacer(1, 10))
            
            # Métricas generales con diseño mejorado
            story.append(Paragraph("MÉTRICAS GENERALES", section_style))
            
            # Crear tabla para métricas generales
            general_metrics_data = [
                ["MÉTRICA", "VALOR"],
                ["Promedio de Medianas Mensuales", format_timedelta(report['avg_duration'])]
            ]
            #comentario de prueba
            general_metrics_table = Table(general_metrics_data, colWidths=[2.5*inch, 2.5*inch])
            general_metrics_table.setStyle(TableStyle([
                # Encabezado
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                # Filas de datos
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                # Bordes
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60'))
            ]))
            story.append(general_metrics_table)
            story.append(Spacer(1, 10))
            
            # Top 5 Issues más largos
            story.append(Paragraph("TOP 5 ISSUES MÁS LARGOS", section_style))
            top_issues_data = [["ISSUE ID", "DURACIÓN"]]
            for item in report["top_issues"]:
                top_issues_data.append([f"Issue #{item['id']}", format_timedelta(item['duration'])])
            
            top_issues_table = Table(top_issues_data, colWidths=[2.5*inch, 2.5*inch])
            top_issues_table.setStyle(TableStyle([
                # Encabezado
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                # Filas de datos
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                # Bordes
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(top_issues_table)
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
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(monthly_table)
            story.append(Spacer(1, 25))
            
            # Métricas generales
            story.append(Paragraph("MÉTRICAS GENERALES", section_style))
            
            general_metrics_data = [
                ["MÉTRICA", "VALOR"],
                ["Promedio de Medianas Mensuales", format_timedelta(report['avg_duration'])]
            ]
            
            general_metrics_table = Table(general_metrics_data, colWidths=[2.5*inch, 2.5*inch])
            general_metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60'))
            ]))
            story.append(general_metrics_table)
            story.append(Spacer(1, 25))
            
            # Top 5 Issues más largos
            story.append(Paragraph("TOP 5 ISSUES MÁS LARGOS", section_style))
            top_issues_data = [["ISSUE ID", "DURACIÓN"]]
            for item in report["top_issues"]:
                top_issues_data.append([f"Issue #{item['id']}", format_timedelta(item['duration'])])
            
            top_issues_table = Table(top_issues_data, colWidths=[2.5*inch, 2.5*inch])
            top_issues_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(top_issues_table)
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
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(monthly_table)
            story.append(Spacer(1, 25))
            
            # Métricas generales
            story.append(Paragraph("MÉTRICAS GENERALES", section_style))
            
            general_metrics_data = [
                ["MÉTRICA", "VALOR"],
                ["Promedio de Medianas Mensuales", format_timedelta(report['avg_duration'])]
            ]
            
            general_metrics_table = Table(general_metrics_data, colWidths=[2.5*inch, 2.5*inch])
            general_metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60'))
            ]))
            story.append(general_metrics_table)
            story.append(Spacer(1, 25))
            
            # Top 5 Issues más largos
            story.append(Paragraph("TOP 5 ISSUES MÁS LARGOS", section_style))
            top_issues_data = [["ISSUE ID", "DURACIÓN"]]
            for item in report["top_issues"]:
                top_issues_data.append([f"Issue #{item['id']}", format_timedelta(item['duration'])])
            
            top_issues_table = Table(top_issues_data, colWidths=[2.5*inch, 2.5*inch])
            top_issues_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#012f60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#012f60')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white])
            ]))
            story.append(top_issues_table)
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

    for definition in report_definitions:
        results, details, monthly_durations = get_done_tickets_by_month(definition["users"])
        
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

            report["monthly_breakdown"] = monthly_breakdown

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
        
        reports_data.append(report)

    # Pasamos la función format_timedelta al template para poder usarla
    return render_template('index.html', reports=reports_data, format_timedelta=format_timedelta, START_DATE=START_DATE)

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
        results, details, monthly_durations = get_done_tickets_by_month(definition["users"])
        
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

            report["monthly_breakdown"] = monthly_breakdown

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

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
from flask import Flask, render_template
import requests
import base64
from datetime import datetime, timedelta
from collections import defaultdict
import math
import statistics
from dotenv import load_dotenv
import os

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
                report["avg_duration"] = sum(durations, timedelta()) / len(durations)
                report["median_duration"] = timedelta(seconds=statistics.median([td.total_seconds() for td in durations]))
                report["top_issues"] = sorted(details, key=lambda x: x['duration'], reverse=True)[:5]
        
        reports_data.append(report)

    # Pasamos la función format_timedelta al template para poder usarla
    return render_template('index.html', reports=reports_data, format_timedelta=format_timedelta, START_DATE=START_DATE)

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
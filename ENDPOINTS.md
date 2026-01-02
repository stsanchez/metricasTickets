# 📍 Documentación de Endpoints - Dashboard de Métricas IT

## Información General
- **Framework**: Flask
- **Puerto**: 5000
- **Host**: 0.0.0.0
- **Proyecto Azure DevOps**: Disbyte Infrastructure
- **Usuarios monitoreados**: Geleser Pimentel, Stefano Sanchez

---

## Endpoints Disponibles

### 1. Dashboard Principal
```
GET /
```
**Función**: `dashboard()`

**Descripción**: Página principal del dashboard que muestra métricas de soporte IT con reportes individuales y combinados.

**Retorna**: 
- Template: `index.html`
- Datos incluidos:
  - Reporte individual de Geleser Pimentel
  - Reporte individual de Stefano Sanchez
  - Reporte combinado de ambos usuarios
  - Desglose mensual de tickets resueltos
  - Métricas de duración promedio y mediana
  - Desglose por prioridad (P1-P4)
  - Límites de SLA por prioridad

**Fecha de inicio**: Definida en `START_DATE` (2025-03-25)

---

### 2. Detalles de Issue
```
GET /issue-details/<issue_id>
```
**Función**: `get_issue_details(issue_id)`

**Descripción**: Obtiene información detallada de un issue específico desde Azure DevOps.

**Parámetros**:
- `issue_id` (int): ID del issue en Azure DevOps

**Retorna** (JSON):
```json
{
  "id": 12345,
  "title": "Título del issue",
  "description": "Descripción del issue",
  "created_date": "2025-01-15T10:30:00Z",
  "created_date_formatted": "15/01/2025 10:30",
  "state_change_date": "2025-01-16T14:20:00Z",
  "state_change_date_formatted": "16/01/2025 14:20",
  "priority": 2,
  "assigned_to": "Nombre del usuario",
  "state": "Done",
  "comments": [
    {
      "id": 1,
      "text": "Comentario del issue",
      "created_date": "2025-01-15T11:00:00Z",
      "created_date_formatted": "15/01/2025 11:00",
      "created_by": "Usuario"
    }
  ]
}
```

**Uso**: Llamado mediante AJAX desde el frontend para mostrar detalles en modales.

---

### 3. Exportar Reporte PDF
```
GET /export-pdf
```
**Función**: `export_pdf()`

**Descripción**: Genera y descarga un reporte PDF con las métricas de soporte IT.

**Retorna**: 
- Archivo PDF descargable
- Nombre: `reporte_metricas_soporte_YYYY-MM-DD.pdf`
- Tipo MIME: `application/pdf`

**Contenido del PDF**:
- Logo de la empresa
- Título: "DASHBOARD DE MÉTRICAS DE SOPORTE IT"
- Página 1: Reporte individual de Geleser Pimentel
- Página 2: Reporte individual de Stefano Sanchez
- Página 3: Reporte combinado
- Cada reporte incluye:
  - Desglose mensual (tabla)
  - Métricas generales
  - Desglose por prioridad

**Fecha de inicio**: Definida en `START_DATE` (2025-03-25)

---

### 4. Reporte Anual
```
GET /annual-report
```
**Función**: `annual_report()`

**Descripción**: Genera el reporte anual completo desde el 01 de enero del año actual.

**Retorna**:
- Template: `annual_report.html`
- Datos incluidos:
  - Reportes anuales de Geleser Pimentel y Stefano Sanchez
  - Desglose mensual cronológico (Enero → Diciembre)
  - Métricas de SLA (Service Level Agreement):
    - Porcentaje de cumplimiento
    - Tickets dentro/fuera de SLA
    - Indicador visual por color
  - **Grand Total**: Suma consolidada de ambos usuarios
  - Gráficos interactivos (Chart.js)
  - Desglose por prioridad

**Fecha de inicio**: `01/01/{año_actual}`

**Límites SLA por Prioridad**:
- P1: 4 horas (advertencia: 2 horas)
- P2: 8 horas (advertencia: 4 horas)
- P3: 2 días hábiles (advertencia: 1 día)
- P4: 5 días hábiles (advertencia: 3 días)

**Colores SLA**:
- Verde (#22c55e): ≥ 70%
- Amarillo (#f59e0b): 60-69%
- Rojo (#ef4444): < 60%

---

### 5. Exportar Reporte Anual PDF
```
GET /export-annual-pdf
```
**Función**: `export_annual_pdf()`

**Descripción**: Genera y descarga el reporte anual como archivo PDF.

**Retorna**:
- Archivo PDF descargable
- Nombre: `reporte_anual_YYYY.pdf`
- Tipo MIME: `application/pdf`

**Contenido del PDF**:
- Similar al reporte mensual pero con datos del año completo
- Ordenamiento cronológico (Enero → Diciembre)
- Métricas anuales consolidadas

**Fecha de inicio**: `01/01/{año_actual}`

---

## Funciones Helper

### Cálculo de Tiempo Laboral
```python
business_time_between(start_dt, end_dt) -> timedelta
```
Calcula el tiempo transcurrido solo dentro del horario laboral:
- **Días hábiles**: Lunes a Viernes
- **Horario**: 8:00 AM - 7:00 PM
- **Zona horaria**: Definida en variable `TIMEZONE`

### Formateo de Duración
```python
format_timedelta(td) -> str
```
Convierte un `timedelta` a formato legible: `"Xd Yh Zm"`

### Límites SLA
```python
get_sla_limit(priority) -> int
get_sla_warning_limit(priority) -> int
```
Retorna los límites de SLA en segundos según la prioridad.

---

## Configuración

### Variables de Entorno (.env)
```bash
PAT=<Personal_Access_Token_Azure_DevOps>
TIMEZONE=America/Argentina/Buenos_Aires  # o UTC
```

### Constantes Principales
```python
ORG_URL = "https://dev.azure.com/Grupo-Disbyte"
PROJECT_NAME = "Disbyte Infrastructure"
USERS_TO_QUERY = ["Stefano Sanchez", "Geleser Pimentel"]
START_DATE = "2025-03-25"
WORK_START_HOUR = 8
WORK_END_HOUR = 19
BUSINESS_DAYS = {0, 1, 2, 3, 4}  # Lunes-Viernes
```

---

## Integración con Azure DevOps

### APIs Utilizadas
- **WIQL API** (v7.1-preview.2): Consultas de work items
- **Batch API** (v7.1-preview.1): Obtención masiva de detalles
- **Work Items API** (v7.1-preview.3): Detalles individuales y comentarios

### Autenticación
- Método: Basic Authentication con PAT (Personal Access Token)
- Header: `Authorization: Basic <base64_encoded_PAT>`

---

## Notas Técnicas

1. **Procesamiento por lotes**: Los tickets se procesan en chunks de 200 para optimizar las llamadas a la API.

2. **Cálculo de métricas**: 
   - Promedio mensual: Calculado como promedio de las medianas mensuales
   - Duración: Solo considera tiempo en horario laboral

3. **Generación de PDF**: Utiliza ReportLab con diseño corporativo en colores #012f60

4. **Renderizado de templates**: Jinja2 con funciones helper pasadas como contexto

---

**Última actualización**: 16/12/2025

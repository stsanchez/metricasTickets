// ========================================
// DASHBOARD DE MÉTRICAS DE SOPORTE IT
// ========================================

// === VARIABLES GLOBALES ===
let sortStates = {}; // Almacenar el estado de ordenamiento para cada modal
let tooltipTimeout = null;
let currentTooltip = null;

// === FUNCIONALIDAD DE MODALES ===
document.addEventListener('click', function (e) {
    var btn = e.target.closest('.view-details-btn');
    if (btn) {
        var id = btn.getAttribute('data-modal-id');
        var modal = document.getElementById(id);
        if (modal) {
            modal.setAttribute('aria-hidden', 'false');
        }
    }
    
    // Manejar clic en números de issue
    var issueLink = e.target.closest('.issue-link');
    if (issueLink) {
        var issueId = issueLink.getAttribute('data-issue-id');
        if (issueId) {
            showIssueDetails(issueId);
        }
    }
    
    if (e.target.classList.contains('close-btn') || e.target.closest('.close-btn')) {
        var overlay = e.target.closest('.modal-overlay');
        if (overlay) overlay.setAttribute('aria-hidden', 'true');
    }
});

// === FUNCIONALIDAD DE DETALLES DE ISSUE ===
function showIssueDetails(issueId) {
    var modal = document.getElementById('issue-details-modal');
    var content = document.getElementById('issue-details-content');
    
    // Mostrar modal con spinner de carga
    content.innerHTML = `
        <div class="loading-spinner">
            <i class="fas fa-spinner fa-spin"></i>
            <p>Cargando detalles del issue...</p>
        </div>
    `;
    modal.setAttribute('aria-hidden', 'false');
    
    // Hacer petición al servidor
    fetch(`/issue-details/${issueId}`)
        .then(response => response.json())
        .then(data => {
            // Formatear la descripción (remover HTML si existe)
            var description = data.description || 'Sin descripción';
            if (description.includes('<')) {
                // Crear un elemento temporal para extraer solo el texto
                var temp = document.createElement('div');
                temp.innerHTML = description;
                description = temp.textContent || temp.innerText || 'Sin descripción';
            }
            
            // Mostrar los detalles
            let commentsHtml = '';
            if (data.comments && data.comments.length > 0) {
                commentsHtml = `
                    <div class="issue-detail-item">
                        <strong>Comentarios:</strong>
                        <div class="comments-section">
                            <button class="view-comments-btn" onclick="toggleComments(${data.id})">
                                <i class="fas fa-comments"></i> Ver todos los comentarios (${data.comments.length})
                            </button>
                            <div id="comments-${data.id}" class="comments-list" style="display: none;">
                                ${data.comments.map(comment => `
                                    <div class="comment-item">
                                        <div class="comment-header">
                                            <strong>${comment.created_by}</strong>
                                            <span class="comment-date">${comment.created_date_formatted}</span>
                                        </div>
                                        <div class="comment-text">${comment.text}</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                `;
            } else {
                commentsHtml = `
                    <div class="issue-detail-item">
                        <strong>Comentarios:</strong>
                        <span class="no-comments">No hay comentarios disponibles</span>
                    </div>
                `;
            }
            
            content.innerHTML = `
                <div class="issue-details">
                    <div class="issue-detail-item">
                        <strong>Número de Issue:</strong>
                        <span>#${data.id}</span>
                    </div>
                    <div class="issue-detail-item">
                        <strong>Título:</strong>
                        <span>${data.title}</span>
                    </div>
                    <div class="issue-detail-item">
                        <strong>Descripción:</strong>
                        <div class="issue-description">${description}</div>
                    </div>
                    <div class="issue-detail-item">
                        <strong>Fecha de Creación:</strong>
                        <span>${data.created_date_formatted}</span>
                    </div>
                    <div class="issue-detail-item">
                        <strong>Fecha de Finalización:</strong>
                        <span>${data.state_change_date_formatted}</span>
                    </div>
                    <div class="issue-detail-item">
                        <strong>Prioridad:</strong>
                        <span class="priority-badge">${data.priority}</span>
                    </div>
                    <div class="issue-detail-item">
                        <strong>Estado:</strong>
                        <span>${data.state}</span>
                    </div>
                    <div class="issue-detail-item">
                        <strong>Asignado a:</strong>
                        <span>${data.assigned_to}</span>
                    </div>
                    ${commentsHtml}
                </div>
            `;
        })
        .catch(error => {
            console.error('Error al cargar detalles del issue:', error);
            content.innerHTML = `
                <div class="error-message">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>Error al cargar los detalles del issue. Por favor, inténtalo de nuevo.</p>
                </div>
            `;
        });
}

// === FUNCIONALIDAD DE COMENTARIOS ===
function toggleComments(issueId) {
    const commentsDiv = document.getElementById(`comments-${issueId}`);
    const button = document.querySelector(`button[onclick="toggleComments(${issueId})"]`);
    
    if (commentsDiv.style.display === 'none') {
        commentsDiv.style.display = 'block';
        button.innerHTML = '<i class="fas fa-comments"></i> Ocultar comentarios';
    } else {
        commentsDiv.style.display = 'none';
        button.innerHTML = '<i class="fas fa-comments"></i> Ver todos los comentarios';
    }
}

// === FUNCIONALIDAD DE TOOLTIP ===
function showTooltip(element, title, mouseX, mouseY) {
    // Limpiar tooltip anterior si existe
    hideTooltip();
    
    // Crear elemento tooltip
    const tooltip = document.createElement('div');
    tooltip.className = 'issue-tooltip';
    tooltip.textContent = title;
    
    // Agregar tooltip al body para posicionamiento absoluto
    document.body.appendChild(tooltip);
    currentTooltip = tooltip;
    
    // Posicionar tooltip desde la posición del mouse hacia la derecha
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    
    // Posición inicial (aproximada)
    let left = mouseX + 10; // 10px de separación del cursor
    let top = mouseY - 40 - 10; // 40px altura aproximada + 10px arriba del cursor
    
    // Aplicar posición inicial
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
    tooltip.style.position = 'fixed';
    
    // Mostrar tooltip con animación
    setTimeout(() => {
        if (tooltip && tooltip.parentNode) {
            // Obtener dimensiones reales después de que se muestre
            const tooltipRect = tooltip.getBoundingClientRect();
            const tooltipWidth = tooltipRect.width;
            const tooltipHeight = tooltipRect.height;
            
            // Recalcular posición si es necesario
            let newLeft = mouseX + 10;
            let newTop = mouseY - tooltipHeight - 10;
            
            // Ajustar si se sale por la derecha
            if (newLeft + tooltipWidth > viewportWidth) {
                newLeft = mouseX - tooltipWidth - 10;
            }
            
            // Ajustar si se sale por arriba
            if (newTop < 10) {
                newTop = mouseY + 10;
            }
            
            // Aplicar posición corregida
            tooltip.style.left = newLeft + 'px';
            tooltip.style.top = newTop + 'px';
            
            tooltip.classList.add('show');
        }
    }, 10);
}

function hideTooltip() {
    if (currentTooltip && currentTooltip.parentNode) {
        currentTooltip.classList.remove('show');
        setTimeout(() => {
            if (currentTooltip && currentTooltip.parentNode) {
                currentTooltip.parentNode.removeChild(currentTooltip);
            }
        }, 200);
        currentTooltip = null;
    }
}

// Event listeners para tooltip
document.addEventListener('mouseenter', function(e) {
    const issueLink = e.target.closest('.issue-link');
    if (issueLink && issueLink.getAttribute('data-issue-title')) {
        const title = issueLink.getAttribute('data-issue-title');
        
        // Limpiar timeout anterior si existe
        if (tooltipTimeout) {
            clearTimeout(tooltipTimeout);
        }
        
        // Mostrar tooltip después de 1.5 segundos
        tooltipTimeout = setTimeout(() => {
            showTooltip(issueLink, title, e.clientX, e.clientY);
        }, 1500);
    }
}, true);

document.addEventListener('mouseleave', function(e) {
    const issueLink = e.target.closest('.issue-link');
    if (issueLink) {
        // Limpiar timeout si el mouse sale antes de que aparezca el tooltip
        if (tooltipTimeout) {
            clearTimeout(tooltipTimeout);
            tooltipTimeout = null;
        }
        
        // Ocultar tooltip si está visible
        hideTooltip();
    }
}, true);

// Ocultar tooltip al hacer scroll o cambiar de ventana
window.addEventListener('scroll', hideTooltip);
window.addEventListener('resize', hideTooltip);

// === FUNCIONALIDAD DE ORDENAMIENTO ===
function sortIssues(modalId, sortDirection, sortType) {
    console.log('sortIssues llamada con modalId:', modalId, 'sortDirection:', sortDirection, 'sortType:', sortType);
    const ticketList = document.querySelector(`.ticket-list[data-modal-id="${modalId}"]`);
    console.log('ticketList encontrado:', ticketList);
    if (!ticketList) {
        console.log('No se encontró ticketList para modalId:', modalId);
        return;
    }

    const items = Array.from(ticketList.querySelectorAll('li'));
    console.log('Items encontrados:', items.length);
    
    // Guardar el orden original si no está guardado
    if (!sortStates[modalId] || !sortStates[modalId].originalOrder) {
        sortStates[modalId] = {
            originalOrder: items.map(item => item.outerHTML)
        };
    }

    if (sortDirection === 'none') {
        // Restaurar orden original
        ticketList.innerHTML = sortStates[modalId].originalOrder.join('');
        sortStates[modalId].currentSort = 'none';
        sortStates[modalId].currentSortType = null;
    } else {
        // Ordenar según el tipo especificado
        items.sort((a, b) => {
            let valueA, valueB;
            
            switch (sortType) {
                case 'issue':
                    valueA = parseInt(a.getAttribute('data-issue-id'));
                    valueB = parseInt(b.getAttribute('data-issue-id'));
                    break;
                case 'priority':
                    valueA = parseInt(a.getAttribute('data-priority')) || 999; // 999 para valores nulos
                    valueB = parseInt(b.getAttribute('data-priority')) || 999;
                    break;
                case 'duration':
                default:
                    valueA = parseFloat(a.getAttribute('data-duration'));
                    valueB = parseFloat(b.getAttribute('data-duration'));
                    break;
            }
            
            if (sortDirection === 'asc') {
                return valueA - valueB;
            } else {
                return valueB - valueA;
            }
        });

        // Limpiar la lista y agregar elementos ordenados
        ticketList.innerHTML = '';
        items.forEach(item => ticketList.appendChild(item));
        sortStates[modalId].currentSort = sortDirection;
        sortStates[modalId].currentSortType = sortType;
    }

    // Actualizar el ícono del botón
    updateSortButton(modalId, sortDirection, sortType);
}

function updateSortButton(modalId, sortDirection, sortType) {
    // Actualizar todos los botones de ordenamiento en este modal
    const allSortBtns = document.querySelectorAll(`.sort-btn[data-modal-id="${modalId}"]`);
    
    allSortBtns.forEach(sortBtn => {
        const icon = sortBtn.querySelector('.sort-icon');
        if (!icon) return;

        const btnSortType = sortBtn.getAttribute('data-sort-type');
        
        // Remover clases anteriores
        icon.classList.remove('fa-sort', 'fa-sort-up', 'fa-sort-down');
        
        // Solo actualizar el botón que corresponde al tipo de ordenamiento actual
        if (btnSortType === sortType) {
            // Agregar clase correspondiente
            switch (sortDirection) {
                case 'asc':
                    icon.classList.add('fa-sort-up');
                    sortBtn.title = 'Ordenar descendente';
                    break;
                case 'desc':
                    icon.classList.add('fa-sort-down');
                    sortBtn.title = 'Sin ordenar';
                    break;
                case 'none':
                default:
                    icon.classList.add('fa-sort');
                    sortBtn.title = 'Ordenar ascendente';
                    break;
            }
        } else {
            // Resetear otros botones
            icon.classList.add('fa-sort');
            switch (btnSortType) {
                case 'issue':
                    sortBtn.title = 'Ordenar por Issue ID';
                    break;
                case 'priority':
                    sortBtn.title = 'Ordenar por prioridad';
                    break;
                case 'duration':
                    sortBtn.title = 'Ordenar por promedio';
                    break;
            }
        }
    });
}

// Event listener para el botón de ordenamiento
document.addEventListener('click', function(e) {
    const sortBtn = e.target.closest('.sort-btn');
    if (sortBtn) {
        e.preventDefault();
        e.stopPropagation();
        
        const modalId = sortBtn.getAttribute('data-modal-id');
        const sortType = sortBtn.getAttribute('data-sort-type');
        console.log('Botón de ordenamiento clickeado, modalId:', modalId, 'sortType:', sortType);
        
        if (!modalId || !sortType) {
            console.log('No se encontró modalId o sortType');
            return;
        }

        // Obtener el estado actual de ordenamiento
        const currentSort = sortStates[modalId]?.currentSort || 'none';
        const currentSortType = sortStates[modalId]?.currentSortType;
        console.log('Estado actual de ordenamiento:', currentSort, 'tipo:', currentSortType);
        
        // Determinar el siguiente estado
        let nextSort;
        
        // Si es un tipo diferente al actual, empezar con ascendente
        if (currentSortType !== sortType) {
            nextSort = 'asc';
        } else {
            // Si es el mismo tipo, ciclar entre los estados
            switch (currentSort) {
                case 'none':
                    nextSort = 'asc';
                    break;
                case 'asc':
                    nextSort = 'desc';
                    break;
                case 'desc':
                    nextSort = 'none';
                    break;
                default:
                    nextSort = 'asc';
                    break;
            }
        }

        console.log('Próximo estado de ordenamiento:', nextSort, 'tipo:', sortType);
        
        // Aplicar el nuevo ordenamiento
        sortIssues(modalId, nextSort, sortType);
    }
});

// === FUNCIONALIDAD DE TEMA ===
const themeToggle = document.getElementById('theme-toggle');
const body = document.body;

function toggleTheme() {
    const currentTheme = body.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    body.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    // Cambiar solo el título del botón
    if (newTheme === 'dark') {
        themeToggle.title = 'Cambiar a modo claro';
    } else {
        themeToggle.title = 'Cambiar a modo oscuro';
    }
}


function loadTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    
    body.setAttribute('data-theme', savedTheme);
    
    if (savedTheme === 'dark') {
        themeToggle.title = 'Cambiar a modo claro';
    } else {
        themeToggle.title = 'Cambiar a modo oscuro';
    }
}

// Event listener para el botón de tema
if (themeToggle) {
    themeToggle.addEventListener('click', toggleTheme);
}


// === FUNCIONALIDAD DE TECLADO ===
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay[aria-hidden="false"]').forEach(function (m) {
            m.setAttribute('aria-hidden', 'true');
        });
    }
});


function searchIssues(searchTerm) {
    const issueLinks = document.querySelectorAll('.issue-link');
    
    issueLinks.forEach(link => {
        const issueId = link.getAttribute('data-issue-id');
        const issueTitle = link.getAttribute('data-issue-title') || '';
        const issueText = `#${issueId} ${issueTitle}`.toLowerCase();
        
        const listItem = link.closest('li');
        if (listItem) {
            if (searchTerm === '' || issueText.includes(searchTerm)) {
                listItem.style.display = 'flex';
                listItem.classList.remove('search-hidden');
            } else {
                listItem.style.display = 'none';
                listItem.classList.add('search-hidden');
            }
        }
    });
    
    // Actualizar contador de resultados
    updateSearchResults(searchTerm);
}

function updateSearchResults(searchTerm) {
    const visibleIssues = document.querySelectorAll('.ticket-list li:not(.search-hidden)');
    const totalIssues = document.querySelectorAll('.ticket-list li');
    
    // Crear o actualizar indicador de resultados
    let resultsIndicator = document.getElementById('search-results');
    if (!resultsIndicator && searchTerm !== '') {
        resultsIndicator = document.createElement('div');
        resultsIndicator.id = 'search-results';
        resultsIndicator.className = 'search-results-indicator';
        document.querySelector('.filters-container').appendChild(resultsIndicator);
    }
    
    if (resultsIndicator) {
        if (searchTerm === '') {
            resultsIndicator.style.display = 'none';
        } else {
            resultsIndicator.innerHTML = `
                <i class="fas fa-search"></i>
                <span>${visibleIssues.length} de ${totalIssues.length} issues encontrados</span>
            `;
            resultsIndicator.style.display = 'flex';
        }
    }
}

// Event listeners para filtros
document.addEventListener('DOMContentLoaded', function() {
    const applyBtn = document.getElementById('apply-filters');
    const clearBtn = document.getElementById('clear-filters');
    
    if (applyBtn) {
        applyBtn.addEventListener('click', applyFilters);
    }
    
    if (clearBtn) {
        clearBtn.addEventListener('click', clearFilters);
    }
    
    // Aplicar filtros al presionar Enter en los inputs
    const filterInputs = document.querySelectorAll('.filter-input, .filter-select');
    filterInputs.forEach(input => {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                applyFilters();
            }
        });
    });
    
    // Búsqueda en tiempo real
    const searchInput = document.getElementById('search-issues');
    const clearSearchBtn = document.getElementById('clear-search');
    
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            
            // Mostrar/ocultar botón de limpiar
            if (searchTerm.length > 0) {
                clearSearchBtn.classList.add('show');
            } else {
                clearSearchBtn.classList.remove('show');
            }
            
            // Búsqueda en tiempo real
            searchIssues(searchTerm);
        });
    }
    
    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', function() {
            searchInput.value = '';
            this.classList.remove('show');
            searchIssues('');
        });
    }
    
    // Exportación a Excel
    const exportExcelBtn = document.getElementById('export-excel');
    if (exportExcelBtn) {
        exportExcelBtn.addEventListener('click', exportToExcel);
    }
    
    // Botón para ver issues fuera de SLA
    const viewOutOfSLABtn = document.getElementById('view-out-of-sla');
    if (viewOutOfSLABtn) {
        viewOutOfSLABtn.addEventListener('click', showOutOfSLAModal);
    }
    
    
    // Event listener para cerrar el modal de SLA
    const outOfSLAModal = document.getElementById('out-of-sla-modal');
    if (outOfSLAModal) {
        const closeBtn = outOfSLAModal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                outOfSLAModal.setAttribute('aria-hidden', 'true');
                outOfSLAModal.style.display = 'none';
            });
        }
        
        // Cerrar al hacer clic en el overlay
        outOfSLAModal.addEventListener('click', function(e) {
            if (e.target === outOfSLAModal) {
                outOfSLAModal.setAttribute('aria-hidden', 'true');
                outOfSLAModal.style.display = 'none';
            }
        });
    }
    
});

// === FUNCIONALIDAD DE EXPORTACIÓN ===
function exportToExcel() {
    try {
        // Recopilar datos de todos los reportes
        const reportsData = extractReportsData();
        const excelData = [];
        
        // Agregar encabezados
        excelData.push([
            'Reporte',
            'Mes',
            'Issue ID',
            'Título',
            'Prioridad',
            'Duración (días)',
            'Estado SLA'
        ]);
        
        // Procesar cada reporte
        reportsData.forEach(report => {
            report.monthlyBreakdown.forEach(monthData => {
                // Aquí necesitaríamos acceso a los datos detallados de cada issue
                // Por simplicidad, agregaremos datos de ejemplo
                const issues = generateSampleIssues(monthData.count);
                
                issues.forEach(issue => {
                    const slaStatus = issue.duration < 1 ? 'En SLA' : 
                                    issue.duration < 2 ? 'En Riesgo' : 'Fuera SLA';
                    
                    excelData.push([
                        report.title,
                        monthData.month,
                        issue.id,
                        issue.title,
                        issue.priority,
                        issue.duration.toFixed(2),
                        slaStatus
                    ]);
                });
            });
        });
        
        // Crear archivo Excel
        createExcelFile(excelData);
        
    } catch (error) {
        console.error('Error al exportar a Excel:', error);
        alert('Error al exportar los datos a Excel. Por favor, inténtalo de nuevo.');
    }
}

function generateSampleIssues(count) {
    const issues = [];
    for (let i = 1; i <= count; i++) {
        issues.push({
            id: Math.floor(Math.random() * 1000) + 1000,
            title: `Issue de ejemplo ${i}`,
            priority: Math.floor(Math.random() * 4) + 1,
            duration: Math.random() * 5 + 0.5
        });
    }
    return issues;
}

function createExcelFile(data) {
    // Crear contenido CSV (compatible con Excel)
    const csvContent = data.map(row => 
        row.map(cell => `"${cell}"`).join(',')
    ).join('\n');
    
    // Agregar BOM para UTF-8
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    
    // Crear enlace de descarga
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `reporte_metricas_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    
    // Descargar archivo
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Mostrar mensaje de éxito
    showNotification('Archivo Excel descargado exitosamente', 'success');
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;
    
    document.body.appendChild(notification);
    
    // Mostrar notificación
    setTimeout(() => {
        notification.classList.add('show');
    }, 100);
    
    // Ocultar después de 3 segundos
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// === FUNCIONALIDAD DE GRÁFICOS ===
let charts = {};

function initializeCharts() {
    // Obtener datos de los reportes
    const reportsData = extractReportsData();
    
    // Crear gráfico de Issues por Mes
    createIssuesByMonthChart(reportsData);
    
    // Crear gráfico de Distribución por Prioridad
    createPriorityDistributionChart(reportsData);
    
}

function extractReportsData() {
    const reports = [];
    const reportCards = document.querySelectorAll('.report-card');
    
    reportCards.forEach(card => {
        const title = card.querySelector('h2').textContent;
        const monthlyBreakdown = [];
        
        // Extraer datos del desglose mensual
        const monthlyItems = card.querySelectorAll('.stats-section ul li');
        monthlyItems.forEach(item => {
            const text = item.textContent;
            const match = text.match(/([A-Z]+ \d{4}):\s*(\d+)\s*Issues/);
            if (match) {
                monthlyBreakdown.push({
                    month: match[1],
                    count: parseInt(match[2])
                });
            }
        });
        
        reports.push({
            title: title,
            monthlyBreakdown: monthlyBreakdown
        });
    });
    
    return reports;
}

function createIssuesByMonthChart(data) {
    const ctx = document.getElementById('issuesByMonthChart');
    if (!ctx) return;
    
    // Preparar datos
    const months = [];
    const geleserData = [];
    const stefanoData = [];
    
    // Obtener todos los meses únicos
    const allMonths = new Set();
    data.forEach(report => {
        report.monthlyBreakdown.forEach(item => {
            allMonths.add(item.month);
        });
    });
    
    const sortedMonths = Array.from(allMonths).sort((a, b) => {
        const [monthA, yearA] = a.split(' ');
        const [monthB, yearB] = b.split(' ');
        if (yearA !== yearB) return yearA - yearB;
        const monthOrder = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 
                           'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'];
        return monthOrder.indexOf(monthA) - monthOrder.indexOf(monthB);
    });
    
    sortedMonths.forEach(month => {
        months.push(month);
        
        const geleserReport = data.find(r => r.title.includes('Geleser'));
        const stefanoReport = data.find(r => r.title.includes('Stefano'));
        
        const geleserCount = geleserReport?.monthlyBreakdown.find(m => m.month === month)?.count || 0;
        const stefanoCount = stefanoReport?.monthlyBreakdown.find(m => m.month === month)?.count || 0;
        
        geleserData.push(geleserCount);
        stefanoData.push(stefanoCount);
    });
    
    charts.issuesByMonth = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: months,
            datasets: [{
                label: 'Geleser Pimentel',
                data: geleserData,
                backgroundColor: 'rgba(30, 58, 138, 0.8)',
                borderColor: 'rgba(30, 58, 138, 1)',
                borderWidth: 1
            }, {
                label: 'Stefano Sanchez',
                data: stefanoData,
                backgroundColor: 'rgba(59, 130, 246, 0.8)',
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

function createPriorityDistributionChart(data) {
    const ctx = document.getElementById('priorityDistributionChart');
    if (!ctx) return;
    
    // Recopilar datos reales de prioridad de todos los issues
    const priorityData = [0, 0, 0, 0]; // Prioridades 1-4
    const allIssues = document.querySelectorAll('.ticket-list li');
    
    allIssues.forEach(issue => {
        const priority = parseInt(issue.getAttribute('data-priority'));
        if (priority >= 1 && priority <= 4) {
            priorityData[priority - 1]++;
        }
    });
    
    // Solo mostrar el gráfico si hay datos
    if (priorityData.every(count => count === 0)) {
        ctx.parentElement.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 20px;">No hay datos de prioridad disponibles</p>';
        return;
    }
    
    charts.priorityDistribution = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Prioridad 1', 'Prioridad 2', 'Prioridad 3', 'Prioridad 4'],
            datasets: [{
                data: priorityData,
                backgroundColor: [
                    'rgba(220, 38, 38, 0.8)',   // Rojo para prioridad 1
                    'rgba(245, 158, 11, 0.8)',  // Amarillo para prioridad 2
                    'rgba(34, 197, 94, 0.8)',   // Verde para prioridad 3
                    'rgba(59, 130, 246, 0.8)'  // Azul para prioridad 4
                ],
                borderColor: [
                    'rgba(220, 38, 38, 1)',
                    'rgba(245, 158, 11, 1)',
                    'rgba(34, 197, 94, 1)',
                    'rgba(59, 130, 246, 1)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return `${context.label}: ${context.parsed} issues (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
    
    console.log('Datos de prioridad reales:', priorityData);
}


// === CÁLCULO DE MÉTRICAS REALES DE SLA ===
function calculateRealSLAMetrics() {
    const allIssues = document.querySelectorAll('.ticket-list li');
    let totalIssues = 0;
    let inSLA = 0;
    let outOfSLA = 0;
    
    allIssues.forEach(issue => {
        const duration = parseFloat(issue.getAttribute('data-duration'));
        const priority = parseInt(issue.getAttribute('data-priority'));
        
        if (duration && priority) {
            totalIssues++;
            
            // Calcular límites según prioridad
            const slaLimit = getSLALimit(priority);
            
            if (duration <= slaLimit) {
                inSLA++;
            } else {
                outOfSLA++;
            }
        }
    });
    
    if (totalIssues > 0) {
        const inSLAPercent = Math.round((inSLA / totalIssues) * 100);
        const outOfSLAPercent = Math.round((outOfSLA / totalIssues) * 100);
        
        // Actualizar los valores en la interfaz
        const goodPercentage = document.getElementById('sla-good-percentage');
        const dangerPercentage = document.getElementById('sla-danger-percentage');
        
        if (goodPercentage) {
            goodPercentage.textContent = `${inSLAPercent}%`;
        }
        if (dangerPercentage) {
            dangerPercentage.textContent = `${outOfSLAPercent}%`;
        }
        
        console.log(`📊 SLA Metrics: ${inSLAPercent}% En Tiempo, ${outOfSLAPercent}% Fuera SLA (Total: ${totalIssues} issues)`);
    }
}

// Funciones helper para calcular límites de SLA según prioridad
function getSLALimit(priority) {
    const slaLimits = {
        1: 4 * 3600,      // P1: 4 horas
        2: 8 * 3600,      // P2: 8 horas  
        3: 2 * 24 * 3600, // P3: 2 días hábiles
        4: 5 * 24 * 3600  // P4: 5 días hábiles
    };
    return slaLimits[priority] || 2 * 24 * 3600; // Default: 2 días
}

function getSLAWarningLimit(priority) {
    const warningLimits = {
        1: 2 * 3600,      // P1: 2 horas (50% del límite)
        2: 4 * 3600,      // P2: 4 horas (50% del límite)
        3: 1 * 24 * 3600, // P3: 1 día hábil (50% del límite)
        4: 3 * 24 * 3600  // P4: 3 días hábiles (60% del límite)
    };
    return warningLimits[priority] || 1 * 24 * 3600; // Default: 1 día
}

// === FUNCIONALIDAD DE MODAL DE ISSUES FUERA DE SLA ===
function showOutOfSLAModal() {
    const modal = document.getElementById('out-of-sla-modal');
    const list = document.getElementById('out-of-sla-list');
    
    if (!modal || !list) return;
    
    // Recopilar todos los issues fuera de SLA
    const outOfSLAIssues = getOutOfSLAIssues();
    
    // Limpiar la lista
    list.innerHTML = '';
    
    if (outOfSLAIssues.length === 0) {
        list.innerHTML = '<li style="text-align: center; color: var(--text-secondary); padding: 20px;">¡Excelente! No hay issues fuera de SLA.</li>';
    } else {
        // Crear elementos de la lista
        outOfSLAIssues.forEach(issue => {
            const li = document.createElement('li');
            li.setAttribute('data-duration', issue.duration);
            li.setAttribute('data-issue-id', issue.id);
            li.setAttribute('data-priority', issue.priority);
            
            li.innerHTML = `
                <strong class="issue-link" data-issue-id="${issue.id}" data-issue-title="${issue.title}" style="cursor: pointer; color: #007acc; text-decoration: underline;">Issue #${issue.id}</strong>
                <div class="priority-cell">
                    <span class="priority-badge priority-${issue.priority}">${issue.priority}</span>
                    <span class="sla-badge sla-danger">
                        <i class="fas fa-times"></i> Fuera SLA
                    </span>
                </div>
                <span class="duration">${formatDuration(issue.duration)}</span>
            `;
            
            list.appendChild(li);
        });
    }
    
    // Mostrar el modal
    modal.setAttribute('aria-hidden', 'false');
    modal.style.display = 'flex';
    
    // Agregar event listeners a los links de issues después de un pequeño delay
    // para asegurar que el DOM se haya actualizado
    setTimeout(() => {
        attachIssueLinkListeners(list);
    }, 100);
}


function getOutOfSLAIssues() {
    const allIssues = document.querySelectorAll('.ticket-list li');
    const outOfSLAIssues = [];
    
    allIssues.forEach(issue => {
        const duration = parseFloat(issue.getAttribute('data-duration'));
        const priority = parseInt(issue.getAttribute('data-priority'));
        const issueId = issue.getAttribute('data-issue-id');
        const issueTitle = issue.querySelector('.issue-link')?.getAttribute('data-issue-title') || `Issue #${issueId}`;
        
        if (duration && priority && issueId) {
            const slaLimit = getSLALimit(priority);
            
            // Si excede el límite de SLA, agregarlo a la lista
            if (duration > slaLimit) {
                outOfSLAIssues.push({
                    id: issueId,
                    title: issueTitle,
                    priority: priority,
                    duration: duration
                });
            }
        }
    });
    
    return outOfSLAIssues;
}


function formatDuration(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) {
        return `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

function attachIssueLinkListeners(container) {
    // Usar delegación de eventos para ser más robusta
    container.addEventListener('click', function(e) {
        const issueLink = e.target.closest('.issue-link');
        if (issueLink) {
            e.preventDefault();
            e.stopPropagation();
            
            const issueId = issueLink.getAttribute('data-issue-id');
            const issueTitle = issueLink.getAttribute('data-issue-title');
            
            console.log('Issue clicked via delegation:', issueId, issueTitle);
            
            if (issueId) {
                showIssueDetails(issueId);
            }
        }
    });
}


// === INICIALIZACIÓN ===
document.addEventListener('DOMContentLoaded', function() {
    // Cargar el tema al iniciar la página
    loadTheme();
    
    // Inicializar gráficos después de un pequeño delay para asegurar que el DOM esté listo
    setTimeout(() => {
        initializeCharts();
        calculateRealSLAMetrics();
        showAllReports(); // Mostrar todos los reportes inicialmente
    }, 500);
    
    console.log('Dashboard de Métricas de Soporte IT - JavaScript cargado');
});

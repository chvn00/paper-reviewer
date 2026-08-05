"""
calendar_co.py — Calendario de días hábiles Colombia 2026
Incluye festivos oficiales según Ley 51 de 1983 (puentes festivos).
"""
from datetime import date, timedelta

# Festivos oficiales Colombia 2026
HOLIDAYS_2026 = {
    date(2026, 1, 1),   # Año Nuevo
    date(2026, 1, 12),  # Reyes Magos (puente — original 6 ene, pasa a lun 12)
    date(2026, 3, 23),  # San José (puente — original 19 mar jue, pasa a lun 23)
    date(2026, 4, 2),   # Jueves Santo
    date(2026, 4, 3),   # Viernes Santo
    date(2026, 5, 1),   # Día del Trabajo
    date(2026, 5, 18),  # Ascensión del Señor (puente — jue 14 may → lun 18)
    date(2026, 6, 8),   # Corpus Christi (puente — jue 4 jun → lun 8)
    date(2026, 6, 15),  # Sagrado Corazón (puente — vie 12 jun → lun 15)
    date(2026, 6, 29),  # San Pedro y San Pablo (ya es lunes)
    date(2026, 7, 20),  # Día de la Independencia
    date(2026, 8, 7),   # Batalla de Boyacá
    date(2026, 8, 17),  # La Asunción (puente — sáb 15 ago → lun 17)
    date(2026, 10, 12), # Día de la Raza (ya es lunes)
    date(2026, 11, 2),  # Todos los Santos (puente — dom 1 nov → lun 2)
    date(2026, 11, 16), # Independencia de Cartagena (puente — mié 11 nov → lun 16)
    date(2026, 12, 8),  # Inmaculada Concepción
    date(2026, 12, 25), # Navidad
}


def is_business_day(d: date) -> bool:
    """Verdadero si d es un día hábil (lun–vie, no festivo)."""
    return d.weekday() < 5 and d not in HOLIDAYS_2026


def add_business_days(start: date, days: int) -> date:
    """Retorna la fecha luego de sumar `days` días hábiles a start."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if is_business_day(current):
            added += 1
    return current


def business_days_elapsed(start: date, reference: date = None) -> int:
    """
    Días hábiles transcurridos desde start (sin contar start)
    hasta reference (o hoy si no se especifica).
    """
    if reference is None:
        reference = date.today()
    if reference <= start:
        return 0
    count = 0
    current = start + timedelta(days=1)
    while current <= reference:
        if is_business_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def business_days_remaining(deadline: date, reference: date = None) -> int:
    """Días hábiles que quedan entre reference (o hoy) y deadline."""
    if reference is None:
        reference = date.today()
    if reference >= deadline:
        return 0
    count = 0
    current = reference + timedelta(days=1)
    while current <= deadline:
        if is_business_day(current):
            count += 1
        current += timedelta(days=1)
    return count

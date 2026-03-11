# /home/admin-rkc/Git/My_cods/project_med/app/services/__init__.py
"""
Пакет app.services — бизнес-логика приложения (сервисы).

Содержит:
- services_all.py: сервисы для работы с пациентами, приёмами, заметками, фото.
- sync_service.py: сервис синхронизации (SyncService) с Яндекс.Диском.
"""

# Импортируем основные сервисы из services_all
from .services_all import (
    PatientService, 
    AppointmentService, 
    NoteService, 
    PhotoService,
)

# Импортируем сервис синхронизации из sync_service
from .sync_service import (
    SyncService,
)

# Экспортируем все классы сервисов
__all__ = [
    'PatientService',
    'AppointmentService',
    'NoteService',
    'PhotoService',
    'SyncService',
]

# Примечание: сервисы инкапсулируют логику работы с БД и внешними ресурсами.

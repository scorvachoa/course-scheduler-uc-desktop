# Course Scheduler UC - Desktop

Aplicación de escritorio en PySide6 para construir y exportar horarios.

## Requisitos

- Python 3.10+
- Dependencias en `requirements.txt`

## Setup local

```bash
pip install -r requirements.txt
python main.py
```

## Core (dependencia compartida)

Este repo depende de `course-scheduler-uc-core` en GitHub.

En `requirements.txt`:

```
course-scheduler-core @ git+https://github.com/scorvachoa/course-scheduler-uc-core@v0.1.0
```

Puedes reemplazar `v0.1.0` por el tag o commit que quieras fijar.

## Datos

- Cursos en `data/cursos.json`.
- El scraping desde la UI actualiza ese archivo.

## Exportación

- PDF: botón **DESCARGAR HORARIO PDF**
- JSON: se genera automáticamente junto al PDF

## Scraping

Para hacer scraping necesitas una cookie válida del portal:

1. Inicia sesión en el portal.
2. Abre DevTools (`F12`) ? pestaña Network.
3. Recarga y abre una request a `/api/academic/`.
4. Copia el header Cookie completo.

Luego en la app:
- Clic en **ACTUALIZAR CURSOS (SCRAPING)**
- Pega la cookie en el popup.

## Generador automático

- Botón: GENERAR HORARIO AUTOMÁTICO
- Selecciona días y cursos
- Genera un horario por bloque y lo aplica automáticamente


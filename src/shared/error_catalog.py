"""
Catálogo centralizado de errores controlados del sistema Pronto.
Usado para documentación y referencia en la interfaz administrativa.
"""

ERROR_CATALOG = {
    "AUTH_001": {
        "title": "Credenciales Inválidas",
        "description": "El correo electrónico o la contraseña proporcionados no coinciden con ningún registro activo.",
        "http_code": 401,
        "solution": "Verificar que el caps lock no esté activado y reintentar. Contactar admin si persiste.",
    },
    "AUTH_002": {
        "title": "Sesión Expirada",
        "description": "La sesión del usuario ha caducado por inactividad o renovación de token.",
        "http_code": 401,
        "solution": "Iniciar sesión nuevamente.",
    },
    "PERM_001": {
        "title": "Acceso Denegado (Rol)",
        "description": "El usuario autenticado no posee el rol necesario para acceder al recurso.",
        "http_code": 403,
        "solution": "Solicitar privilegios elevados al Super Admin.",
    },
    "CHECK_001": {
        "title": "Orden Sin Ítems",
        "description": "Intento de procesar una orden o checkout sin productos seleccionados.",
        "http_code": 400,
        "solution": "Añadir productos al carrito antes de confirmar.",
    },
    "MENU_001": {
        "title": "Categoría Duplicada",
        "description": "Intento de crear una categoría con un nombre que ya existe.",
        "http_code": 409,
        "solution": "Usar otro nombre para la categoría.",
    },
    "MENU_002": {
        "title": "Producto Inexistente",
        "description": "Referencia a un ID de producto que no se encuentra en la base de datos.",
        "http_code": 404,
        "solution": "Actualizar el menú o verificar IDs.",
    },
    "PAYMENT_001": {
        "title": "Pago Fallido",
        "description": "La transacción de pago fue rechazada por la pasarela o error de red.",
        "http_code": 402,
        "solution": "Intentar con otro método de pago.",
    },
    "SYSTEM_001": {
        "title": "Error Interno",
        "description": "Excepción no controlada en el servidor (Bug o falla de infraestructura).",
        "http_code": 500,
        "solution": "Revisar logs del servidor 6081/6082.",
    },
}

SERVICE_INFO_6081 = {
    "name": "Employee Operations & Admin Portal",
    "port": 6081,
    "description": (
        "Aplicación central para el personal del restaurante. "
        "Maneja el ciclo completo de órdenes (Mesero -> Cocina -> Caja), "
        "gestión de mesas, configuración del menú, usuarios y reportes."
    ),
    "modules": [
        "Dashboard (Tiempo real)",
        "Waiter Board (Toma de órdenes)",
        "Kitchen Display (Estados de preparación)",
        "Admin Panel (Configuración y Usuarios)",
        "API REST (Endpoints seguros)",
    ],
    "status": "Operational",
}

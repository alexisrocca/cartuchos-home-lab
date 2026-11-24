STAGES = {
    "locate": ("Localizando el Home Lab", "Buscando el servidor en Tailscale."),
    "power-check": ("Consultando el enchufe", "Comprobando el estado del enchufe en Tuya."),
    "power-on": ("Encendiendo el Home Lab", "Tuya está dando corriente al servidor."),
    "boot": ("Esperando el arranque", "Esperando a que GNOME y Hermes estén listos."),
    "select": ("Enviando la selección", "Indicándole al Home Lab qué juego abrir."),
    "prepare": ("Preparando la sesión", "Hermes está preparando la pantalla virtual."),
    "connect": ("Conectando Hestia", "Estableciendo la conexión de video y audio."),
    "wait-game": ("Esperando el juego", "El sonido se activará cuando aparezca el juego."),
    "shaders": ("Procesando sombreadores", "Steam está preparando la caché gráfica del juego."),
    "sign-in": ("Iniciar sesión en el launcher", "Completá el inicio de sesión en la ventana que se abrirá."),
    "video": ("Abriendo la transmisión", "La sesión está lista para mostrarse."),
}
OPTIONAL = {"power-check", "power-on", "boot", "select", "wait-game", "shaders", "sign-in"}


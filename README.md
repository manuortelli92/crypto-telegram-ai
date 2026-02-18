# Crypto Telegram AI

Un bot de Telegram que utiliza inteligencia artificial para proporcionar funciones específicas relacionadas con el análisis de criptomonedas.

## Características
- Respuestas automatizadas utilizando Gemini AI.
- Generación de contenidos personalizada para usuarios.
- Optimizado para integrarse con servicios en la nube como Heroku.

## Instalación

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/manuortelli92/crypto-telegram-ai.git
   cd crypto-telegram-ai
   ```

2. **Configurar el entorno virtual (opcional pero recomendado):**
   ```bash
   python -m venv venv
   source venv/bin/activate # En Linux/Mac
   venv\\Scripts\\activate  # En Windows
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar las variables de entorno:**
   Asegúrate de establecer las siguientes variables (por ejemplo, utilizando un archivo `.env`):
   - `GEMINI_API_KEY`: Tu clave de API.
   - `TELEGRAM_BOT_TOKEN`: Token del bot de Telegram.

## Uso

Ejecuta el bot con el siguiente comando:
```bash
python bot.py
```

Abre Telegram y envía mensajes al bot para interactuar.

## Contribuciones
Las contribuciones están abiertas. Por favor, realiza un fork del repositorio, haz cambios en tu propio branch y envíanos un pull request.

## Licencia
Este proyecto está bajo la licencia MIT. [Consulta el archivo de licencia](LICENSE) para más detalles.
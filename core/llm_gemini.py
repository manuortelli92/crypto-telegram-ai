def gemini_render(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: La variable GEMINI_API_KEY está vacía.")
        return None
        
    try:
        genai.configure(api_key=api_key)
        
        # Configuración del modelo con System Instruction nativa
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=system_prompt # Mucho más efectivo
        )
        
        response = model.generate_content(
            user_prompt,
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
        )
        
        return response.text

    except Exception as e:
        # Esto te dirá exactamente QUÉ está fallando
        error_msg = str(e)
        if "API_KEY_INVALID" in error_msg:
            logger.error("🚨 La clave API es incorrecta.")
        elif "location" in error_msg.lower():
            logger.error("🚨 Tu región (IP) no está admitida por Google API.")
        else:
            logger.error(f"🚨 Error inesperado: {error_msg}")
        return None
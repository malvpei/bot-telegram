"""Twenty copy variants per student pack, grounded in the tips being rendered."""

GOGRADUATE_SOCIAL_COPY_IDS = [f"student-copy-{index:02d}" for index in range(1, 21)]

GOGRADUATE_SOCIAL_TITLES: dict[str, tuple[str, ...]] = {
    "students-01": (
        "Estudiar más no siempre es estudiar mejor",
        "Cierra los apuntes y descubre qué recuerdas de verdad",
        "Releer no te dice todo lo que sabes",
        "Tu próximo repaso empieza antes de abrir el tema",
        "De reconocer una frase a saber explicarla",
        "No concentres todos tus repasos en una tarde",
        "Vuelve mañana a lo que hoy te cuesta",
        "Mezcla ejercicios para aprender a elegir el método",
        "La pregunta importante: ¿por qué usarías ese método?",
        "Pon a prueba tu memoria antes de seguir leyendo",
        "Menos vueltas al mismo párrafo, más respuestas propias",
        "Un repaso que empieza con preguntas, no con subrayadores",
        "Divide los repasos y comprueba qué puedes recuperar",
        "Saber resolver también es saber elegir cómo empezar",
        "Lo que no recuerdas te ayuda a organizar el estudio",
        "Tus apuntes deberían servir para comprobar, no para adivinar",
        "Prueba otro tipo de ejercicio antes de dar el tema por hecho",
        "Una forma de estudiar con más intención y menos piloto automático",
        "Prepara el siguiente repaso a partir de tus dudas",
        "GoGraduate y hábitos de estudio que puedes poner en práctica",
    ),
    "students-02": (
        "Deja de copiar apuntes y empieza a hacerte preguntas",
        "Cada apartado puede convertirse en una pregunta",
        "Inténtalo antes de mirar cómo se resuelve",
        "No confundas tener la solución con saber llegar a ella",
        "Tus dudas también necesitan sitio en el repaso",
        "¿Qué respondes solo y qué necesita una pista?",
        "El primer intento te muestra dónde te atascas",
        "Convierte los títulos del tema en pequeñas pruebas",
        "Repasar solo lo fácil deja tus dudas para el examen",
        "No abras la respuesta antes de pensar la tuya",
        "Busca el paso donde cambia tu razonamiento",
        "Estudia con preguntas que puedas corregir después",
        "Un apunte copiado no sustituye a una respuesta propia",
        "Vuelve más a lo que todavía necesitas que te expliquen",
        "Empieza por una pregunta, no por otra página de resumen",
        "Haz un intento y después usa los apuntes para comprobarlo",
        "Detecta tus puntos débiles antes de dar por terminado el tema",
        "La próxima sesión puede empezar por lo que no supiste responder",
        "Tus apuntes pueden convertirse en un entrenamiento de preguntas",
        "Preguntas, primeros intentos y tu profesor GoGraduate",
    ),
    "students-03": (
        "La hoja en blanco también sirve para estudiar",
        "¿Qué queda del tema cuando cierras los apuntes?",
        "Corrige el porqué, no solo la respuesta",
        "Vuelve al tema otro día y comprueba qué recuerdas",
        "Empieza el repaso escribiendo tus ideas de memoria",
        "Una respuesta corregida necesita una explicación",
        "La parte que no sale en la hoja merece otro repaso",
        "No des el tema por aprendido justo después de leerlo",
        "Deja una pequeña prueba para dentro de unos días",
        "Entender un fallo te da una pista para el siguiente intento",
        "Una hoja vacía puede ayudarte a decidir por dónde empezar",
        "Antes de mirar el resumen, escribe tu propio mapa del tema",
        "La pregunta no termina cuando ves la solución correcta",
        "Comprueba tu memoria cuando el tema ya no está tan reciente",
        "Revisar errores también es explicar qué confundiste",
        "Haz que el siguiente repaso responda a tus dudas de hoy",
        "¿Lo sabes o necesitas que los apuntes te lo recuerden?",
        "Escribe, comprueba y vuelve a intentarlo otro día",
        "Prepara preguntas para saber qué has retenido",
        "De la hoja en blanco a tus apuntes con GoGraduate",
    ),
    "students-04": (
        "Si cambia la pregunta, ¿sigues sabiendo la respuesta?",
        "Prueba con otro ejemplo antes de dar una idea por entendida",
        "Esconde la respuesta y haz tu propio intento",
        "Elige la estrategia antes de empezar a calcular",
        "Aprender una frase no es lo mismo que usar la idea",
        "Tus tarjetas necesitan preguntas, no respuestas a la vista",
        "¿Qué método usarías si nadie te diera una pista?",
        "Cambia el ejemplo y comprueba si entiendes el concepto",
        "No destapes la solución antes de responder",
        "Antes de hacer cuentas, decide qué necesitas resolver",
        "Una pregunta distinta puede revelar una duda nueva",
        "Practica elegir el método, no solo repetir sus pasos",
        "Pon la explicación detrás de la tarjeta",
        "Comprueba si puedes aplicar lo que has memorizado",
        "La primera línea del ejercicio puede ser tu estrategia",
        "No dependas siempre del mismo ejemplo de los apuntes",
        "Haz tu intento antes de descubrir la respuesta",
        "Prepara un repaso que te obligue a decidir",
        "De repetir una definición a resolver con ella",
        "Ejemplos nuevos, respuestas ocultas y GoGraduate",
    ),
}

GOGRADUATE_SOCIAL_INTROS = (
    "Que un tema te suene familiar no es lo mismo que responder sin pistas. "
    "Estas {count_word} ideas te ayudan a poner a prueba tus apuntes antes del examen.",
    "Antes de preparar otro resumen, dedica un momento a comprobar qué sabes "
    "explicar por tu cuenta. Guarda estos {count_word} consejos para tu próxima sesión.",
    "Si no sabes por dónde empezar a repasar, empieza por lo que todavía no "
    "puedes responder. Aquí tienes {count_word} ideas para organizar ese intento.",
    "Tus apuntes pueden servir para algo más que leer: también para preguntar, "
    "comprobar y corregir. Prueba estas {count_word} ideas con el tema que estás preparando.",
    "Una sesión de estudio también puede dejarte preguntas claras para mañana. "
    "Estos {count_word} consejos conectan lo que haces hoy con el siguiente repaso.",
    "¿Qué harías si te preguntaran el tema sin dejarte mirar? Estas "
    "{count_word} ideas te invitan a ensayar una respuesta propia y después comprobarla.",
    "No necesitas aplicar todo a la vez. Elige uno de estos {count_word} "
    "consejos, pruébalo con tus apuntes y observa dónde necesitas más práctica.",
    "Dar un tema por terminado y poder explicarlo son cosas distintas. "
    "Revisa estos {count_word} consejos antes de cerrar tu próxima sesión de estudio.",
    "Haz sitio para tus dudas en el repaso, no solo para lo que ya sale fácil. "
    "Estas {count_word} ideas parten de tus propias respuestas, intentos y apuntes.",
    "Una buena pregunta puede darte un punto de partida para estudiar. "
    "Aquí tienes {count_word} consejos para trabajar el contenido con más intención.",
    "Tu siguiente sesión no tiene por qué repetir exactamente la anterior. "
    "Conserva estos {count_word} consejos y decide qué vas a comprobar esta vez.",
    "Cuando te atasques, identifica qué parte necesitas entender en lugar "
    "de pasar de página sin más. Estos {count_word} consejos te dan formas de practicarlo.",
    "Empieza con un tema concreto y una respuesta que quieras comprobar. "
    "Aplica estas {count_word} ideas a tus apuntes sin convertir el repaso en otra lista interminable.",
    "El siguiente intento también cuenta, especialmente cuando el primero "
    "te deja dudas. Estos {count_word} consejos te ayudan a preparar qué probar después.",
    "Estudiar con intención empieza por saber qué quieres comprobar. "
    "Repasa estas {count_word} ideas y elige una para la asignatura que más te cuesta.",
    "Antes de buscar una respuesta en tus apuntes, intenta construir la tuya. "
    "Aquí tienes {count_word} consejos para darle más protagonismo a ese primer intento.",
    "Una página marcada puede seguir escondiendo dudas. Usa estos "
    "{count_word} consejos para revisar lo que puedes explicar y lo que aún necesitas trabajar.",
    "Preparar un examen también consiste en reconocer cuándo necesitas "
    "otra explicación. Estas {count_word} ideas ponen el foco en tu forma de practicar.",
    "Llévate de esta sesión algo que puedas comprobar en la siguiente. "
    "Estos {count_word} consejos unen preguntas, práctica y trabajo con tus apuntes.",
    "Guarda esta imagen para convertir tu próximo repaso en una prueba "
    "de lo que sabes. Aquí van {count_word} consejos con GoGraduate como tu profesor.",
)

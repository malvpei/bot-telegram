from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import lcm

from app.models import Language


class AdviceBackground(str, Enum):
    BLACK = "black"
    WHITE = "white"
    ILLUSTRATED = "illustrated"
    EDITORIAL = "editorial"


@dataclass(frozen=True)
class AdviceTip:
    title: str
    body: str


ADVICE_BACKGROUNDS: tuple[AdviceBackground, ...] = (
    AdviceBackground.BLACK,
    AdviceBackground.WHITE,
    AdviceBackground.ILLUSTRATED,
    AdviceBackground.EDITORIAL,
)

ADVICE_PACKS: dict[Language, tuple[tuple[AdviceTip, ...], ...]] = {
    Language.ES: (
        (
            AdviceTip(
                "no copies el producto, copia el ángulo",
                "dos tiendas pueden vender lo mismo y obtener resultados muy "
                "distintos por cómo explican el problema.",
            ),
            AdviceTip(
                "automatiza la gestión de pedidos",
                "usa ChatGPT para clasificar pedidos, preparar respuestas y detectar "
                "incidencias; revisa cada acción antes de enviarla.",
            ),
            AdviceTip(
                "muestra el producto antes del segundo 2",
                "si tardas demasiado en enseñar qué vendes, muchos se irán sin "
                "entender el anuncio.",
            ),
            AdviceTip(
                "encuentra ganadores antes de lanzar",
                "usa Dropradar para encontrar productos ganadores ya validados y "
                "empezar con una oportunidad mucho más segura.",
            ),
        ),
        (
            AdviceTip(
                "no persigas productos virales",
                "cuando aparecen por todas partes, normalmente ya hay demasiadas "
                "tiendas vendiéndolos.",
            ),
            AdviceTip(
                "delega la gestión repetitiva",
                "ChatGPT puede resumir consultas, priorizar pedidos y dejar respuestas "
                "listas para revisar, para que atiendas más clientes sin perder el control.",
            ),
            AdviceTip(
                "añade un pack bastante más caro",
                "aunque casi nadie lo compre, hará que la opción intermedia parezca "
                "más atractiva.",
            ),
            AdviceTip(
                "deja de elegir productos a ciegas",
                "Dropradar encuentra productos ganadores validados para que empieces "
                "con una oportunidad más segura.",
            ),
        ),
        (
            AdviceTip(
                "busca anuncios antiguos, no solo virales",
                "si una tienda mantiene el mismo anuncio durante semanas, "
                "probablemente está consiguiendo resultados.",
            ),
            AdviceTip(
                "convierte pedidos en un flujo de trabajo",
                "conecta ChatGPT a tus herramientas para extraer datos de pedidos, "
                "avisar de retrasos y crear tareas de seguimiento.",
            ),
            AdviceTip(
                "lee los comentarios antes de elegir",
                "si muchos preguntan dónde comprarlo, existe interés que aún no se "
                "ha convertido en ventas.",
            ),
            AdviceTip(
                "encuentra productos que ya venden",
                "usa Dropradar para detectar productos ganadores antes de perder "
                "tiempo copiando a otras tiendas.",
            ),
        ),
        (
            AdviceTip(
                "no estudies únicamente anuncios virales",
                "un anuncio activo durante semanas puede ser mejor señal que uno con "
                "visitas durante un solo día.",
            ),
            AdviceTip(
                "usa un asistente para tus operaciones",
                "ChatGPT te ayuda a organizar pedidos, redactar mensajes y mantener "
                "el seguimiento al día, mientras tú supervisas las decisiones importantes.",
            ),
            AdviceTip(
                "haz que un pack destaque claramente",
                "una opción más cara puede hacer que tu oferta principal parezca "
                "económica sin cambiar su precio.",
            ),
            AdviceTip(
                "elige un producto ganador",
                "Dropradar te ayuda a encontrar productos ganadores validados antes "
                "de invertir en anuncios.",
            ),
        ),
    ),
    Language.EN: (
        (
            AdviceTip(
                "don't copy the product, copy the angle",
                "two stores can sell the same thing and get very different results "
                "because of how they explain the problem.",
            ),
            AdviceTip(
                "automate your order admin",
                "use ChatGPT to sort orders, draft replies and flag issues; review "
                "every action before it is sent.",
            ),
            AdviceTip(
                "show the product before second 2",
                "if you wait too long to reveal what you sell, people leave before "
                "understanding the ad.",
            ),
            AdviceTip(
                "find winners before launching",
                "use Dropradar to find validated winning products and start with a "
                "much safer opportunity.",
            ),
        ),
        (
            AdviceTip(
                "don't chase viral products",
                "when they appear everywhere, there are usually already too many "
                "stores selling them.",
            ),
            AdviceTip(
                "delegate repetitive admin",
                "ChatGPT can summarize questions, prioritize orders and prepare replies "
                "for review, so you can serve more customers without losing control.",
            ),
            AdviceTip(
                "add a much more expensive bundle",
                "even if almost nobody buys it, your middle option will feel more "
                "attractive.",
            ),
            AdviceTip(
                "stop picking products blindly",
                "Dropradar finds validated winning products so you can start with a "
                "stronger opportunity.",
            ),
        ),
        (
            AdviceTip(
                "study old ads, not only viral ones",
                "if a store keeps the same ad for weeks, it is probably producing "
                "results.",
            ),
            AdviceTip(
                "turn orders into a workflow",
                "connect ChatGPT to your tools to extract order details, flag delays "
                "and create follow-up tasks.",
            ),
            AdviceTip(
                "read comments before choosing",
                "if people keep asking where to buy it, there is interest that has "
                "not become sales yet.",
            ),
            AdviceTip(
                "find products already selling",
                "use Dropradar to spot validated winners before wasting time copying "
                "other stores.",
            ),
        ),
        (
            AdviceTip(
                "don't only study viral ads",
                "an ad running for weeks can be a stronger signal than one getting "
                "views for a single day.",
            ),
            AdviceTip(
                "use an operations assistant",
                "ChatGPT can organize orders, draft messages and keep follow-up on "
                "track while you supervise the important decisions.",
            ),
            AdviceTip(
                "make one bundle look clearly better",
                "a more expensive option can make your main offer feel cheaper "
                "without changing its price.",
            ),
            AdviceTip(
                "choose a validated winner",
                "Dropradar helps you find validated winning products before you spend "
                "on ads.",
            ),
        ),
    ),
}

# The editorial layout mirrors the five-row reference.  It reuses each
# four-tip pack and inserts one extra practical tip before the Dropradar
# recommendation, so the branded recommendation always closes the list.
ADVICE_EDITORIAL_EXTRA_TIPS: dict[Language, tuple[AdviceTip, ...]] = {
    Language.ES: (
        AdviceTip(
            "prueba la oferta antes de escalar",
            "valida el interés con poco presupuesto antes de aumentar la inversión.",
        ),
        AdviceTip(
            "calcula el margen real",
            "incluye envío, comisiones y devoluciones antes de decidir si merece la pena.",
        ),
        AdviceTip(
            "comprueba al proveedor",
            "pide una muestra y revisa la entrega antes de prometer tiempos al cliente.",
        ),
        AdviceTip(
            "compara tres ángulos",
            "prueba beneficio, problema y demostración para descubrir qué mensaje vende.",
        ),
    ),
    Language.EN: (
        AdviceTip(
            "test the offer before scaling",
            "validate interest with a small budget before increasing your spend.",
        ),
        AdviceTip(
            "calculate the real margin",
            "include shipping, fees and returns before deciding if it is worth testing.",
        ),
        AdviceTip(
            "check the supplier first",
            "order a sample and review delivery before promising times to customers.",
        ),
        AdviceTip(
            "compare three angles",
            "test benefit, problem and demonstration to discover which message sells.",
        ),
    ),
}

ADVICE_EXTERNAL_PHRASES: dict[Language, str] = {
    Language.ES: (
        "un dropshipper millonario me contó la regla número #1 para vender fácilmente"
    ),
    Language.EN: (
        "A millionaire dropshipper told me rule number #1 for selling easily"
    ),
}

ADVICE_SOCIAL_TITLES: dict[Language, tuple[tuple[str, ...], ...]] = {
    Language.ES: (
        (
            "la regla #1 no es perseguir visitas",
            "el consejo detrás del hook: explica mejor el problema",
            "cómo comprobar si una idea merece una prueba",
        ),
        (
            "antes de lanzar, separa señal de ruido",
            "una pregunta de cliente vale más que una moda",
            "qué revisar cuando un producto parece demasiado fácil",
        ),
        (
            "lo que los anuncios antiguos te enseñan",
            "organiza el trabajo antes de buscar más apps",
            "lee la conversación, no solo las visitas",
        ),
        (
            "elige con criterio antes de gastar",
            "la regla #1 también se aplica a la gestión",
            "qué significa validar de verdad",
        ),
    ),
    Language.EN: (
        (
            "the #1 rule is not chasing views",
            "the advice behind the hook: explain the problem better",
            "how to check whether an idea deserves a test",
        ),
        (
            "before launching, separate signal from noise",
            "one customer question beats a passing trend",
            "what to check when a product looks too easy",
        ),
        (
            "what older ads can teach you",
            "organize the work before adding more apps",
            "read the conversation, not just the views",
        ),
        (
            "choose with evidence before spending",
            "the #1 rule also applies to operations",
            "what real validation actually means",
        ),
    ),
}

ADVICE_SOCIAL_DESCRIPTIONS: dict[Language, tuple[tuple[str, ...], ...]] = {
    Language.ES: (
        (
            "El hook habla de una regla número 1 para vender fácilmente, pero la regla no "
            "es encontrar un producto mágico ni perseguir el vídeo que acumula más visitas. "
            "La parte útil es aprender a mirar qué hay detrás de esas visitas. Dos tiendas "
            "pueden vender el mismo producto y tener resultados opuestos porque una explica "
            "un problema concreto y la otra solo enseña el objeto. Antes de lanzar, pregunta "
            "qué necesidad resuelve, qué frase usaría un cliente para describirla y qué "
            "ángulo hace que la oferta sea fácil de entender en los primeros segundos. "
            "También conviene revisar si hay señales repetidas de demanda, si otros anuncios "
            "llevan tiempo activos y si el margen soporta envío, comisiones, devoluciones y "
            "pruebas. ChatGPT puede ayudarte a ordenar pedidos, resumir preguntas y preparar "
            "respuestas, pero no decide si el producto es bueno ni sustituye la revisión. "
            "Usa los datos de Dropradar como una fuente más, escribe una hipótesis sencilla y "
            "prueba una sola cosa cada vez. Así el consejo del hook deja de ser una promesa y "
            "se convierte en un método para aprender antes de gastar. Antes de abrir el "
            "administrador de anuncios, anota qué parte de la oferta quieres observar y qué "
            "resultado sería suficiente para continuar. Puede ser una respuesta concreta en "
            "los comentarios, un coste por clic razonable o simplemente comprobar que la gente "
            "entiende el beneficio sin que tengas que explicarlo cinco veces. Si el resultado "
            "no aparece, no significa automáticamente que el producto no sirva: quizá el ángulo "
            "no se entiende, el precio no encaja o el tráfico no es el adecuado. Lo importante "
            "es que el siguiente cambio responda a una pregunta y no a la ansiedad de ver pocas "
            "visitas. Esa forma de trabajar hace que cada prueba deje una pista útil, incluso "
            "cuando toca descartar la idea.",
            "El hook promete una regla sencilla, y la primera lección es no confundir "
            "visibilidad con demanda. Si dos tiendas venden lo mismo, la diferencia suele "
            "estar en el ángulo: una habla de un problema que el cliente reconoce y la otra "
            "solo enumera características. Antes de copiar un anuncio, escribe en una frase "
            "qué problema resuelve la oferta y por qué alguien la elegiría ahora. Después "
            "comprueba si esa idea aparece en comentarios, reseñas, anuncios que siguen "
            "activos y búsquedas de productos parecidos. ChatGPT puede servirte para ordenar "
            "las preguntas de los clientes y preparar una primera respuesta, pero revisa todo "
            "antes de enviarlo. La herramienta ayuda a organizar el trabajo; el criterio sigue "
            "siendo tuyo.",
            "La regla del hook se entiende mejor cuando la conviertes en preguntas concretas. "
            "¿Qué problema estoy explicando? ¿El cliente lo reconoce sin que tenga que leer "
            "un párrafo? ¿Hay una señal de interés que no dependa de un único vídeo viral? "
            "¿Puedo probar el ángulo con un presupuesto pequeño y saber qué aprendí? Mira "
            "también cómo se presentan otras ofertas: el mismo producto puede parecer útil, "
            "irrelevante o caro según la historia que lo acompaña. Si usas Dropradar, no lo "
            "trates como una respuesta automática, sino como una forma de comparar señales "
            "antes de construir la tienda. Elegir mejor no elimina el riesgo, pero evita que "
            "cada lanzamiento empiece desde una intuición distinta.",
        ),
        (
            "El hook habla de vender fácilmente, pero elegir un producto no debería ser una "
            "apuesta. Cuando algo aparece por todas partes, la visibilidad puede significar "
            "interés real o simplemente que todos están copiando la misma tendencia. Antes de "
            "lanzar, separa esas dos cosas. Mira cuánto tiempo llevan activos los anuncios, "
            "lee reseñas que mencionen problemas concretos y observa qué preguntas hacen los "
            "clientes antes de comprar. Una pregunta repetida puede darte una mejora para la "
            "oferta; una queja repetida puede decirte qué promesa no debes hacer. ChatGPT sirve "
            "para agrupar consultas, priorizar pedidos y preparar respuestas para revisar, no "
            "para responder sin supervisión ni para inventar datos de envío. Si pruebas packs, "
            "usa una opción más completa para entender qué valora la gente, pero calcula el "
            "margen real de cada una. Una herramienta de investigación como Dropradar puede "
            "ayudarte a comparar señales, aunque la decisión final debe salir de una hipótesis "
            "que puedas comprobar. También revisa el coste de equivocarte: cuánto dinero pierdes "
            "si el proveedor se retrasa, si una devolución se come el margen o si necesitas "
            "cambiar el creativo después de una semana. Pensar en esos escenarios no es ser "
            "negativo, es poner un límite a la prueba antes de que la emoción tome la decisión. "
            "Un producto puede tener interés y aun así no ser una buena opción para tu tienda "
            "por sus plazos, su soporte o la dificultad de explicar la diferencia. El objetivo "
            "no es encontrar una garantía, sino saber qué condiciones deben cumplirse para que "
            "tenga sentido seguir investigando.",
            "Una pregunta real de un cliente suele ser más útil que otra moda en el feed. El "
            "hook invita a buscar una regla rápida, pero el trabajo consiste en escuchar qué "
            "dudas se repiten: tiempos de entrega, tamaño, compatibilidad, devoluciones o "
            "resultado esperado. Esas preguntas pueden convertirse en una explicación más "
            "clara y en un anuncio que responda antes de que la persona abandone. ChatGPT puede "
            "resumir conversaciones y dejar respuestas preparadas para revisar, mientras tú "
            "compruebas que el tono, el precio y la información sean correctos. No uses una "
            "respuesta automática para tapar una oferta confusa. Primero arregla la promesa, "
            "después automatiza la parte repetitiva. Esa secuencia suele ahorrar más tiempo que "
            "añadir otra aplicación al flujo.",
            "Cuando un producto parece demasiado fácil de vender, haz una pausa antes de "
            "lanzarlo. Comprueba si el margen admite incidencias, si el proveedor puede cumplir "
            "los plazos y si la oferta sigue teniendo sentido sin depender de un descuento "
            "permanente. Revisa también si la opción más cara aporta algo real o solo sirve "
            "para que la intermedia parezca barata. El consejo del hook no es gastar menos por "
            "miedo, sino aprender qué parte de la propuesta merece una prueba. Dropradar puede "
            "aportar contexto sobre productos y señales de mercado; ChatGPT puede ayudarte a "
            "ordenar la información y preparar tareas. Ninguna de las dos cosas reemplaza leer "
            "las condiciones del proveedor ni hablar con tus clientes.",
        ),
        (
            "El hook menciona una regla #1, y una forma práctica de aplicarla es mirar el "
            "tiempo. Un anuncio que sigue activo durante semanas no demuestra que sea rentable, "
            "pero sí aporta una señal distinta a un pico de visitas de un solo día. Observa "
            "qué promete, a quién parece dirigirse y cómo presenta el producto. Lee los "
            "comentarios: las preguntas repetidas suelen señalar una necesidad y las quejas "
            "repetidas pueden revelar una oportunidad para mejorar la oferta. ChatGPT puede "
            "convertir esas conversaciones en una lista de temas, organizar los pedidos y "
            "preparar un seguimiento, siempre con revisión antes de actuar. Usa los datos de "
            "Dropradar para comparar productos y no para justificar una decisión que ya tomaste. "
            "La meta es llegar al lanzamiento con una pregunta clara, un criterio para medir y "
            "un límite para decidir cuándo parar. Si un anuncio sigue activo, intenta entender "
            "qué está haciendo bien en lugar de copiarlo entero: la primera frase, el orden de "
            "la demostración, la objeción que responde o la prueba social que utiliza. Después "
            "adapta solo una de esas ideas a tu producto y observa si cambia la respuesta. La "
            "investigación se vuelve mucho más útil cuando produce una hipótesis que puedes "
            "explicar a otra persona. Si no puedes explicar por qué estás probando algo, todavía "
            "no has encontrado la señal que necesitas.",
            "Antes de buscar otra aplicación, ordena el trabajo que ya tienes. El consejo del "
            "hook no va de acumular herramientas, sino de dejar de improvisar. Define qué pasa "
            "cuando entra un pedido, quién revisa el pago, cómo se comprueba el envío y cuándo "
            "se informa al cliente. ChatGPT puede ayudarte a extraer datos, crear una lista de "
            "tareas y redactar un mensaje de seguimiento, pero las reglas del negocio deben "
            "estar claras antes de automatizar nada. Una bandeja llena no se arregla con más "
            "apps si nadie sabe qué prioridad tiene cada conversación. Empieza por un flujo "
            "pequeño, mide dónde se atasca y mejora solo ese paso. La simplicidad no es una "
            "limitación: es la forma de saber qué parte del proceso está fallando.",
            "Los comentarios explican algo que las visitas no pueden explicar por sí solas. El "
            "hook habla de vender fácilmente, pero una tienda se entiende mejor cuando lees lo "
            "que la gente pregunta antes de comprar: dónde se envía, cuánto tarda, qué incluye "
            "y qué ocurre si no encaja. Agrupa esas preguntas y decide cuáles deben aparecer en "
            "la página, en el anuncio y en el mensaje posterior al pedido. ChatGPT puede ayudarte "
            "a ordenar la conversación y a proponer borradores, pero comprueba cada dato con el "
            "proveedor. La automatización ahorra tiempo cuando parte de información fiable; si "
            "no, solo multiplica una respuesta incorrecta. Mira también anuncios antiguos y "
            "productos con ventas repetidas para separar una oportunidad de un momento de ruido.",
        ),
        (
            "El hook presenta una regla para vender fácilmente, pero la parte más útil ocurre "
            "antes de gastar en anuncios. Elegir con criterio significa saber qué estás "
            "intentando comprobar: demanda, margen, claridad de la oferta o capacidad del "
            "proveedor. Si no defines esa pregunta, cualquier resultado parece una señal y "
            "acabas cambiando producto, precio y creativo al mismo tiempo. Revisa si el anuncio "
            "se entiende rápido, si el pack principal tiene una razón clara y si puedes "
            "responder a las dudas después del pago. ChatGPT puede ayudarte a organizar el "
            "seguimiento, preparar respuestas y convertir una lista de pedidos en tareas, pero "
            "deja la aprobación final en tus manos. Dropradar puede servir como contexto para "
            "investigar productos; no lo conviertas en una promesa de ventas. Empieza con una "
            "prueba pequeña, define qué resultado esperas y escribe qué aprenderás incluso si "
            "no hay pedidos. Ese criterio es más útil que perseguir otra tendencia. Una prueba "
            "pequeña también te permite revisar la operación completa: confirmar el pago, preparar "
            "el pedido, informar del envío y contestar una incidencia sin improvisar. Si la "
            "venta llega pero el proceso posterior se rompe, todavía no tienes una oferta lista "
            "para crecer. Apunta las dudas que aparecen, los pasos que repites y las respuestas "
            "que te gustaría tener preparadas. Ahí es donde una automatización sencilla puede "
            "ahorrarte tiempo sin convertir la tienda en una cadena de mensajes genéricos.",
            "La regla #1 también se aplica a la gestión diaria: no se trata de hacer todo más "
            "rápido, sino de decidir qué merece atención primero. Cuando entra un pedido, "
            "separa confirmación, preparación, envío, incidencias y seguimiento. ChatGPT puede "
            "resumir mensajes, detectar temas repetidos y dejar borradores para revisar, pero "
            "no debería inventar un plazo ni enviar una respuesta que no hayas comprobado. "
            "Automatizar un proceso confuso solo hace que el error viaje más rápido. Empieza "
            "con una tarea repetitiva, define una regla sencilla y revisa durante unos días si "
            "realmente te ahorra tiempo. El hook habla de vender fácilmente; este es el trabajo "
            "menos visible que permite mantener una venta cuando por fin llega.",
            "Validar de verdad no significa encontrar una certeza absoluta. Significa reunir "
            "suficientes señales para tomar una decisión pequeña y saber qué resultado haría "
            "que siguieras o pararas. Comprueba el interés, el margen, la entrega, las dudas "
            "del cliente y la forma de explicar el beneficio. Después prueba un ángulo y no "
            "cambies cinco variables a la vez. El consejo del hook funciona cuando te ayuda a "
            "reducir incertidumbre, no cuando se usa como otra promesa de dinero fácil. Puedes "
            "usar Dropradar para investigar y ChatGPT para ordenar notas, pedidos y respuestas, "
            "pero conserva la revisión humana y anota lo que aprendiste. Un método sencillo que "
            "puedas repetir vale más que una lista de herramientas que solo consultas el día del "
            "lanzamiento.",
        ),
    ),
    Language.EN: (
        (
            "The hook talks about a number one rule for selling easily, but the rule is not "
            "finding a magical product or chasing the video with the most views. The useful "
            "part is learning what sits behind those views. Two stores can sell the same item "
            "and get opposite results because one explains a specific problem while the other "
            "only shows the object. Before launching, ask what need it solves, what phrase a "
            "customer would use to describe it and which angle makes the offer clear in the "
            "first seconds. Check whether demand signals repeat, whether other ads have stayed "
            "active and whether the margin can absorb shipping, fees, returns and testing. "
            "ChatGPT can help sort orders, summarize questions and prepare replies, but it does "
            "not decide whether the product is good or replace your review. Use Dropradar as one "
            "source, write a simple hypothesis and test one thing at a time. That turns the hook "
            "from a promise into a method for learning before you spend. Before opening the ad "
            "manager, write down what you want to observe and what result would be enough to keep "
            "going. It might be a clear question in the comments, a reasonable cost per click or "
            "simply proof that people understand the benefit without a long explanation. If the "
            "result does not appear, it does not automatically mean the product is wrong: the angle "
            "may be unclear, the price may not fit or the traffic may be mismatched. The important "
            "part is making the next change answer a question instead of reacting to a low view "
            "count. That approach makes every test leave a useful clue, even when the right decision "
            "is to drop the idea.",
            "The hook promises a simple rule, and the first lesson is not confusing visibility "
            "with demand. If two stores sell the same product, the difference is often the angle: "
            "one names a problem the customer recognizes and the other lists features. Before "
            "copying an ad, write one sentence explaining the problem and why someone would choose "
            "the offer now. Then check whether that idea appears in comments, reviews, ads that "
            "remain active and searches for similar products. ChatGPT can help organize customer "
            "questions and prepare a first reply, but review everything before sending it. The "
            "tool helps organize the work; the judgment is still yours.",
            "The rule from the hook becomes useful when you turn it into concrete questions. What "
            "problem am I explaining? Can a customer recognize it without reading a paragraph? Is "
            "there a signal of interest that does not depend on one viral video? Can I test the "
            "angle with a small budget and know what I learned? Look at how other offers are "
            "framed: the same product can feel useful, irrelevant or expensive depending on the "
            "story around it. If you use Dropradar, treat it as a way to compare signals before "
            "building the store, not as an automatic answer. Better selection does not remove risk, "
            "but it stops every launch from starting with a different guess.",
        ),
        (
            "The hook talks about selling easily, but choosing a product should not be a guess. "
            "When something appears everywhere, visibility can mean real interest or simply that "
            "everyone is copying the same trend. Before launching, separate those two things. "
            "Look at how long ads have stayed active, read reviews that mention specific problems "
            "and notice which questions customers ask before buying. A repeated question can show "
            "how to improve the offer; a repeated complaint can show which promise not to make. "
            "ChatGPT can group questions, prioritize orders and prepare replies for review, but "
            "not answer without supervision or invent shipping information. If you test bundles, "
            "use a more complete option to learn what people value, but calculate the real margin "
            "for each one. A research tool such as Dropradar can help compare signals, while the "
            "final decision should come from a hypothesis you can actually test. Also estimate the "
            "cost of being wrong: what happens if the supplier is late, a return consumes the margin "
            "or the creative needs to change after a week? Thinking through those cases is not being "
            "negative; it sets a limit before excitement makes the decision. A product can have "
            "interest and still be a poor fit for your store because of delivery times, support or "
            "how hard the difference is to explain. The aim is not finding a guarantee, but knowing "
            "which conditions need to be true before you keep researching.",
            "One real customer question is often more useful than another passing trend. The hook "
            "invites you to look for a quick rule, but the work is listening for repeated doubts: "
            "delivery times, sizing, compatibility, returns or the result someone expects. Those "
            "questions can become a clearer explanation and an ad that answers before the person "
            "leaves. ChatGPT can summarize conversations and prepare replies for review, while you "
            "check that the tone, price and information are correct. Do not use an automatic reply "
            "to hide a confusing offer. Fix the promise first, then automate the repetitive part. "
            "That sequence usually saves more time than adding another app to the workflow.",
            "When a product looks too easy to sell, pause before launching it. Check whether the "
            "margin can absorb issues, whether the supplier can meet delivery times and whether the "
            "offer still makes sense without a permanent discount. Also check whether the expensive "
            "option adds real value or only makes the middle one look cheap. The hook's advice is "
            "not to spend less out of fear; it is to learn which part of the offer deserves a test. "
            "Dropradar can add context about products and market signals, while ChatGPT can help "
            "organize information and prepare tasks. Neither replaces reading supplier terms or "
            "speaking with customers.",
        ),
        (
            "The hook mentions a number one rule, and one practical way to apply it is to watch "
            "time. An ad that stays active for weeks does not prove profitability, but it gives a "
            "different signal from a one-day spike in views. Look at the promise, the audience and "
            "the way the product is presented. Read comments: repeated questions can point to a "
            "need, while repeated complaints can reveal an opportunity to improve the offer. "
            "ChatGPT can turn those conversations into topics, organize orders and prepare follow-up, "
            "always with review before action. Use Dropradar to compare products, not to justify a "
            "decision you already made. The goal is to launch with a clear question, a way to measure "
            "it and a limit for deciding when to stop. If an ad stays active, try to understand what "
            "it does well instead of copying the whole thing: the opening line, the order of the demo, "
            "the objection it answers or the proof it uses. Adapt only one idea to your product and "
            "watch whether the response changes. Research becomes much more useful when it produces a "
            "hypothesis you can explain to someone else. If you cannot explain why you are testing "
            "something, you have not found the signal you need yet.",
            "Before looking for another app, organize the work you already have. The hook is not "
            "about collecting tools; it is about stopping the improvisation. Define what happens "
            "when an order arrives, who checks payment, how shipping is confirmed and when the "
            "customer is updated. ChatGPT can extract details, create a task list and draft a follow-up "
            "message, but the business rules need to be clear before you automate anything. A full "
            "inbox is not fixed by more apps when nobody knows the priority of each conversation. "
            "Start with a small workflow, find where it stalls and improve that step only. Simplicity "
            "is not a limitation; it is how you find the part of the process that is actually failing.",
            "Comments reveal something views cannot explain on their own. The hook talks about selling "
            "easily, but a store becomes clearer when you read what people ask before buying: where it "
            "ships, how long it takes, what is included and what happens if it does not fit. Group those "
            "questions and decide which belong on the page, in the ad and in the post-order message. "
            "ChatGPT can help organize the conversation and suggest drafts, but check every detail with "
            "the supplier. Automation saves time when it starts with reliable information; otherwise it "
            "only multiplies a wrong answer. Look at older ads and products with repeated sales to separate "
            "an opportunity from a moment of noise.",
        ),
        (
            "The hook presents a rule for selling easily, but the useful part happens before you "
            "spend on ads. Choosing with evidence means knowing what you are trying to check: demand, "
            "margin, offer clarity or supplier capacity. Without that question, every result looks like "
            "a signal and you end up changing the product, price and creative at once. Check whether "
            "the ad is easy to understand, whether the main bundle has a clear reason to exist and whether "
            "you can answer questions after payment. ChatGPT can organize follow-up, prepare replies and "
            "turn an order list into tasks, but keep final approval in your hands. Dropradar can provide "
            "research context; do not turn it into a sales promise. Start with a small test, define the "
            "result you expect and write down what you will learn even if no orders arrive. That criterion "
            "is more useful than chasing another trend. A small test also lets you review the full "
            "operation: confirming payment, preparing the order, updating shipping and answering an "
            "issue without improvising. If the sale arrives but the post-purchase process breaks, the "
            "offer is not ready to grow yet. Note the questions that appear, the steps you repeat and "
            "the replies you would like to have ready. That is where a simple automation can save time "
            "without turning the store into a stream of generic messages.",
            "The number one rule also applies to daily operations: it is not about doing everything faster, "
            "but deciding what deserves attention first. When an order arrives, separate confirmation, "
            "preparation, shipping, issues and follow-up. ChatGPT can summarize messages, detect repeated "
            "topics and draft replies for review, but it should not invent a deadline or send information "
            "you have not checked. Automating a confusing process only makes the error travel faster. Start "
            "with one repetitive task, define a simple rule and watch for a few days to see whether it saves "
            "time. The hook talks about selling easily; this is the less visible work that helps you keep a "
            "sale once it finally arrives.",
            "Real validation does not mean finding absolute certainty. It means gathering enough signals to "
            "make a small decision and knowing what result would make you continue or stop. Check interest, "
            "margin, delivery, customer questions and the way the benefit is explained. Then test one angle "
            "without changing five variables at once. The hook's advice works when it reduces uncertainty, "
            "not when it becomes another promise of easy money. Use Dropradar for research and ChatGPT to "
            "organize notes, orders and replies, but keep human review and write down what you learned. A "
            "simple method you can repeat is worth more than a list of tools you only open on launch day.",
        ),
    ),
}

ADVICE_SOCIAL_HASHTAGS: dict[Language, tuple[str, ...]] = {
    Language.ES: (
        "#dropshipping",
        "#productosganadores",
        "#ecommerce",
        "#shopify",
        "#dropradar",
    ),
    Language.EN: (
        "#dropshipping",
        "#winningproducts",
        "#ecommerce",
        "#shopify",
        "#dropradar",
    ),
}

ADVICE_VISUAL_CYCLE_LENGTH = (
    len(ADVICE_BACKGROUNDS) * len(ADVICE_PACKS[Language.ES])
)
ADVICE_SOCIAL_CYCLE_LENGTH = (
    len(ADVICE_PACKS[Language.ES])
    * min(
        len(pack_titles)
        for language_titles in ADVICE_SOCIAL_TITLES.values()
        for pack_titles in language_titles
    )
)


def advice_social_copy(
    language: Language,
    pack_index: int,
    rotation_index: int | None = None,
) -> tuple[str, str, list[str]]:
    """Return TikTok-ready title, description and hashtags for an advice card."""
    titles = ADVICE_SOCIAL_TITLES[language]
    descriptions = ADVICE_SOCIAL_DESCRIPTIONS[language]
    hashtags = ADVICE_SOCIAL_HASHTAGS[language]
    pack = max(0, int(pack_index)) % len(titles)
    cycle = 0 if rotation_index is None else max(0, int(rotation_index)) // len(titles)
    variant = cycle % len(titles[pack])
    return (
        titles[pack][variant],
        descriptions[pack][variant],
        list(hashtags),
    )

ADVICE_ILLUSTRATED_TITLES: dict[Language, tuple[str, str]] = {
    Language.ES: (
        "4 reglas para vender más con dropshipping",
        "pequeños detalles que la mayoría de tiendas ignora",
    ),
    Language.EN: (
        "4 rules to sell more with dropshipping",
        "small details most stores overlook",
    ),
}

ADVICE_ROTATION_CYCLE_LENGTH = lcm(
    ADVICE_VISUAL_CYCLE_LENGTH,
    ADVICE_SOCIAL_CYCLE_LENGTH,
)


def advice_selection(
    phase: int,
    language: Language,
) -> tuple[AdviceBackground, tuple[AdviceTip, ...], int]:
    normalized_phase = max(0, int(phase)) % ADVICE_ROTATION_CYCLE_LENGTH
    packs = ADVICE_PACKS[language]
    background_count = len(ADVICE_BACKGROUNDS)
    background = ADVICE_BACKGROUNDS[normalized_phase % background_count]
    # Four backgrounds and four packs would otherwise remain locked together.
    # Shifting the pack after every complete background lap makes every visual
    # template meet every advice pack during the 16-step visual cycle.
    pack_index = (
        normalized_phase + normalized_phase // background_count
    ) % len(packs)
    tips = packs[pack_index]
    if background == AdviceBackground.EDITORIAL:
        tips = (
            *tips[:-1],
            ADVICE_EDITORIAL_EXTRA_TIPS[language][pack_index],
            tips[-1],
        )
    return (
        background,
        tips,
        pack_index,
    )


def format_advice_script(tips: tuple[AdviceTip, ...]) -> str:
    return "\n\n".join(
        f"{index}. {tip.title}\n{tip.body}"
        for index, tip in enumerate(tips, start=1)
    )


def validate_advice_content() -> None:
    expected_pack_count = len(ADVICE_PACKS[Language.ES])
    for language, packs in ADVICE_PACKS.items():
        if len(packs) != expected_pack_count:
            raise ValueError("Los idiomas no tienen el mismo número de guiones tipo 4.")
        editorial_extras = ADVICE_EDITORIAL_EXTRA_TIPS[language]
        if len(editorial_extras) != len(packs):
            raise ValueError(
                f"Faltan consejos para la plantilla editorial en {language.value}."
            )
        social_titles = ADVICE_SOCIAL_TITLES[language]
        social_descriptions = ADVICE_SOCIAL_DESCRIPTIONS[language]
        if len(social_titles) != len(packs) or len(social_descriptions) != len(packs):
            raise ValueError(
                f"Faltan descripciones sociales para los consejos en {language.value}."
            )
        if len(ADVICE_SOCIAL_HASHTAGS[language]) < 3:
            raise ValueError(
                f"Los consejos en {language.value} necesitan hashtags relacionados."
            )
        for pack_titles, pack_descriptions in zip(
            social_titles,
            social_descriptions,
            strict=True,
        ):
            if len(pack_titles) < 3 or len(pack_titles) != len(pack_descriptions):
                raise ValueError(
                    f"Cada pack de consejos en {language.value} necesita títulos y "
                    "descripciones suficientes para rotar."
                )
        for tips in packs:
            if len(tips) != 4:
                raise ValueError("Cada guion tipo 4 debe contener exactamente 4 consejos.")
            final_body = tips[-1].body.lower()
            if "dropradar" not in final_body:
                raise ValueError(
                    f"El cuarto consejo tipo 4 en {language.value} debe nombrar Dropradar."
                )
            if not any(term in final_body for term in ("ganador", "winner", "winning")):
                raise ValueError(
                    f"El cuarto consejo tipo 4 en {language.value} debe presentar "
                    "Dropradar como herramienta de productos ganadores."
                )


validate_advice_content()

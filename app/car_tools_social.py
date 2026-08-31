from __future__ import annotations

from app.car_tools import CAR_TOOLS_HOOK
from app.models import SocialCopy


def _copy(
    title: str,
    description: str,
    hashtags: tuple[str, ...],
) -> SocialCopy:
    return SocialCopy(
        title=title,
        description=description,
        hashtags=list(hashtags),
        hook=CAR_TOOLS_HOOK,
    )


CAR_TOOLS_SOCIAL_COPIES: tuple[SocialCopy, ...] = (
    _copy(
        "4 apps que todo conductor debería conocer",
        (
            "Conducir puede ser mucho más sencillo con las herramientas adecuadas. "
            "RadarBot te ayuda con los radares, ParkEz con el aparcamiento, Waze "
            "con el tráfico y Google Maps con tus rutas y paradas. Guárdalo para "
            "tu próximo viaje."
        ),
        ("#coches", "#conducir", "#apps", "#carretera", "#movilidad"),
    ),
    _copy(
        "Las apps que no pueden faltar en tu coche",
        (
            "Si pasas tiempo al volante, estas cuatro apps pueden facilitarte el "
            "día: RadarBot para anticiparte a los radares, ParkEz para buscar "
            "aparcamiento, Waze para esquivar atascos y Google Maps para planificar "
            "rutas y descubrir lugares. ¿Cuál utilizas más?"
        ),
        (
            "#coches",
            "#conductores",
            "#appsutiles",
            "#trafico",
            "#aparcamiento",
            "#viajes",
        ),
    ),
    _copy(
        "4 herramientas para conducir con menos complicaciones",
        (
            "Una buena ruta no depende solo del destino. RadarBot puede avisarte de "
            "radares durante el trayecto; ParkEz te ayuda a localizar zonas de "
            "aparcamiento; Waze adapta la ruta según el tráfico; y Google Maps "
            "resulta útil para viajes largos, restaurantes, gasolineras y otros "
            "puntos de interés. Cuatro herramientas distintas para resolver "
            "problemas cotidianos al volante."
        ),
        (
            "#coches",
            "#conduccion",
            "#carretera",
            "#apps",
            "#movilidad",
            "#viajesencoche",
        ),
    ),
    _copy(
        "Tu copiloto digital: 4 apps imprescindibles",
        (
            "Antes de arrancar, prepara también tu móvil. En este carrusel reunimos "
            "cuatro herramientas pensadas para distintas partes del viaje: RadarBot "
            "para estar atento a los radares, ParkEz para encontrar aparcamiento, "
            "Waze para elegir una ruta con menos tráfico y Google Maps para "
            "orientarte y localizar sitios durante el camino. No hacen lo mismo, "
            "pero juntas pueden ahorrarte vueltas, tiempo y más de un quebradero de "
            "cabeza. Guarda el vídeo para consultarlo cuando lo necesites."
        ),
        (
            "#coches",
            "#appsparacoche",
            "#conducir",
            "#trafico",
            "#parking",
            "#navegacion",
            "#viajes",
        ),
    ),
    _copy(
        "Conduce mejor con estas 4 aplicaciones",
        (
            "Hay trayectos que se complican por un atasco, una zona donde no aparece "
            "aparcamiento o una ruta mal planificada. Por eso merece la pena conocer "
            "estas cuatro apps. RadarBot está enfocada en los avisos de radares; "
            "ParkEz ayuda a identificar opciones para aparcar en la calle; Waze busca "
            "rutas teniendo en cuenta el tráfico; y Google Maps combina navegación "
            "con información de negocios y lugares de interés. Puedes usar una u otra "
            "según el momento, o llevar las cuatro preparadas para cubrir casi todo el "
            "viaje. Comparte este carrusel con esa persona que siempre está conduciendo."
        ),
        (
            "#coches",
            "#conductores",
            "#apps",
            "#movilidad",
            "#trafico",
            "#aparcamiento",
            "#googlemaps",
            "#waze",
            "#carretera",
        ),
    ),
    _copy(
        "4 apps para ahorrar tiempo cuando conduces",
        (
            "Moverse en coche no consiste únicamente en seguir una carretera. "
            "También hay que vigilar los radares, reaccionar ante el tráfico, "
            "encontrar dónde aparcar y localizar servicios en ruta. Este carrusel "
            "reúne una app para cada necesidad: RadarBot ofrece avisos relacionados "
            "con radares; ParkEz puede ayudarte cuando llega el momento de buscar "
            "aparcamiento; Waze propone rutas basadas en lo que ocurre en la vía; y "
            "Google Maps sirve tanto para navegar como para encontrar restaurantes, "
            "gasolineras, tiendas o puntos de interés. Son herramientas sencillas, "
            "pero pueden marcar la diferencia en los desplazamientos diarios y en los "
            "viajes largos. Guarda esta lista antes de volver a salir a la carretera."
        ),
        (
            "#coches",
            "#conducir",
            "#appsutiles",
            "#trafico",
            "#aparcamiento",
            "#rutas",
            "#viajesencoche",
            "#movilidad",
        ),
    ),
    _copy(
        "Radar, parking, tráfico y rutas: todo en 4 apps",
        (
            "Cada trayecto tiene sus propios obstáculos. A veces lo difícil es evitar "
            "una vía congestionada; otras, encontrar un sitio donde dejar el coche al "
            "llegar. Y en un viaje largo también interesa saber dónde parar, comer o "
            "repostar. Estas cuatro aplicaciones cubren esos momentos desde enfoques "
            "diferentes. RadarBot ayuda a mantenerte informado sobre radares durante la "
            "conducción. ParkEz está pensada para facilitar la búsqueda de aparcamiento "
            "en la calle. Waze utiliza información del tráfico para orientar la ruta. "
            "Google Maps completa el conjunto con navegación, distancias y lugares "
            "útiles alrededor del recorrido. No sustituyen la atención ni las normas "
            "de circulación, pero sí pueden ayudarte a organizar mejor el viaje. ¿Ya "
            "llevas las cuatro instaladas o todavía te falta alguna?"
        ),
        (
            "#coches",
            "#seguridadvial",
            "#conductores",
            "#appsparaconducir",
            "#trafico",
            "#parking",
            "#mapas",
            "#carretera",
            "#viajes",
        ),
    ),
    _copy(
        "Estas 4 apps te solucionan el viaje en coche",
        (
            "Salir con tiempo no siempre garantiza llegar sin problemas: puede "
            "aparecer tráfico, cambiar la ruta o resultar imposible aparcar cerca del "
            "destino. Tener las herramientas correctas preparadas permite reaccionar "
            "mejor. RadarBot está orientada a los avisos de radares y puede ayudarte a "
            "conducir con mayor previsión. ParkEz se centra en la búsqueda de "
            "aparcamiento, especialmente cuando das vueltas por una zona que no "
            "conoces. Waze es una opción muy práctica para consultar el estado del "
            "tráfico y valorar recorridos alternativos. Google Maps ayuda a planificar "
            "el viaje, seguir indicaciones y encontrar desde una gasolinera hasta un "
            "restaurante o un cine. En lugar de pedirle todo a una sola aplicación, "
            "este conjunto reparte las tareas entre cuatro opciones especializadas. "
            "Úsalas de forma segura, configura el trayecto antes de arrancar y mantén "
            "siempre la atención en la carretera."
        ),
        (
            "#coches",
            "#apps",
            "#conduccionsegura",
            "#trafico",
            "#aparcamiento",
            "#rutas",
            "#navegacion",
            "#viajar",
            "#conductores",
        ),
    ),
    _copy(
        "El kit digital que necesitas para conducir",
        (
            "El móvil puede convertirse en un copiloto muy útil si eliges bien las "
            "aplicaciones y las configuras antes de iniciar la marcha. En este "
            "carrusel encontrarás cuatro herramientas para situaciones reales que se "
            "repiten al conducir. RadarBot puede mantenerte al tanto de avisos de "
            "radares, algo especialmente útil en recorridos que no conoces. ParkEz "
            "está orientada a localizar aparcamiento y evitar tantas vueltas al llegar. "
            "Waze permite revisar el tráfico y adaptar la ruta cuando la circulación se "
            "complica. Google Maps es una alternativa completa para navegar, preparar "
            "viajes largos y encontrar negocios o servicios cercanos. La idea no es "
            "mirar la pantalla constantemente, sino salir con el recorrido preparado y "
            "contar con información útil cuando la necesites. Puedes combinar las cuatro "
            "según el tipo de desplazamiento: una ruta diaria al trabajo, una visita a "
            "otra ciudad o unas vacaciones por carretera. Guarda este vídeo y envíaselo "
            "a quien acaba de comprarse un coche."
        ),
        (
            "#coches",
            "#appsparacoche",
            "#conductores",
            "#movilidad",
            "#trafico",
            "#aparcamiento",
            "#viajes",
            "#carretera",
            "#tecnologia",
        ),
    ),
    _copy(
        "4 aplicaciones que hacen más fácil cualquier trayecto",
        (
            "Un trayecto cómodo empieza mucho antes de poner el coche en marcha. "
            "Revisar la ruta, anticipar zonas con tráfico y saber dónde vas a aparcar "
            "puede evitar prisas al final. Estas cuatro aplicaciones cubren buena parte "
            "de ese proceso. RadarBot se ocupa de los avisos relacionados con radares "
            "para que conduzcas con más información y respetes los límites. ParkEz puede "
            "ayudarte a localizar posibilidades de aparcamiento cuando llegas a una zona "
            "concurrida. Waze destaca por mostrar incidencias y ajustar el recorrido "
            "según el estado de la circulación. Google Maps resulta especialmente "
            "práctico para calcular rutas, organizar viajes largos y encontrar "
            "restaurantes, gasolineras, cines u otros lugares. Cada una aporta algo "
            "distinto y por eso funcionan bien como conjunto. Antes de conducir, coloca "
            "el móvil en un soporte adecuado, configura la navegación y evita manipularlo "
            "durante la marcha. La tecnología ayuda de verdad cuando se utiliza con "
            "responsabilidad. ¿Cuál de estas cuatro recomendarías a otro conductor?"
        ),
        (
            "#coches",
            "#conducir",
            "#seguridadvial",
            "#appsutiles",
            "#trafico",
            "#parking",
            "#googlemaps",
            "#waze",
            "#radarbot",
            "#viajesencoche",
        ),
    ),
    _copy(
        "Las 4 apps que convierten tu móvil en copiloto",
        (
            "Hay días en los que conducir parece una suma de pequeños problemas: una "
            "calle cortada, tráfico inesperado, un radar en una zona desconocida o "
            "veinte minutos buscando dónde dejar el coche. Para esos momentos conviene "
            "tener un kit digital preparado. RadarBot puede ofrecer avisos de radares y "
            "ayudarte a mantener una conducción más consciente. ParkEz se enfoca en "
            "encontrar aparcamiento en la calle, una tarea especialmente pesada en áreas "
            "concurridas. Waze consulta el estado de las vías y propone recorridos que "
            "pueden evitar parte del tráfico. Google Maps permite planificar la ruta "
            "completa y localizar paradas útiles, como gasolineras, restaurantes, "
            "alojamientos o tiendas. Estas aplicaciones no eliminan todos los "
            "imprevistos, pero sí reúnen información que permite tomar mejores decisiones "
            "antes y durante el trayecto. Lo recomendable es seleccionar el destino y "
            "revisar las opciones con el vehículo detenido; después, deja que las "
            "indicaciones te guíen sin apartar la vista de la carretera. Guarda el "
            "carrusel para preparar tu próximo desplazamiento y compártelo con tu grupo "
            "de viajes."
        ),
        (
            "#coches",
            "#conductores",
            "#appsparaconducir",
            "#movilidad",
            "#trafico",
            "#aparcamiento",
            "#rutas",
            "#viajes",
            "#carretera",
            "#tecnologia",
            "#conduccionsegura",
        ),
    ),
    _copy(
        "Menos vueltas y mejores rutas con estas 4 apps",
        (
            "¿Cuánto tiempo perdemos al volante por no preparar el trayecto? Un atasco "
            "que podía evitarse, varias vueltas buscando aparcamiento o una parada "
            "improvisada porque no sabemos dónde hay una gasolinera. Este carrusel reúne "
            "cuatro aplicaciones pensadas para reducir ese tipo de fricciones. RadarBot "
            "está especializada en avisos de radares y aporta información útil en rutas "
            "habituales o desconocidas. ParkEz puede facilitar la búsqueda de "
            "aparcamiento en la calle cuando el destino está en una zona con mucha "
            "demanda. Waze ayuda a conocer el tráfico y a comparar alternativas en "
            "función de lo que sucede en la vía. Google Maps completa la selección con "
            "navegación, cálculo de distancias y búsqueda de lugares, desde restaurantes "
            "hasta cines o estaciones de servicio. Puedes utilizarlas como un pequeño "
            "sistema: comprueba el tráfico, elige el recorrido, identifica dónde "
            "aparcarás y deja previstas las paradas. No necesitas tener las cuatro "
            "abiertas a la vez; basta con escoger la más adecuada para cada momento. "
            "Configúralas siempre antes de iniciar la marcha y recuerda que ninguna "
            "notificación es más importante que mantener la atención. Si sueles viajar "
            "en coche, guarda esta guía: te servirá tanto para el trayecto diario como "
            "para la próxima escapada."
        ),
        (
            "#coches",
            "#appsutiles",
            "#conducir",
            "#trafico",
            "#aparcamiento",
            "#navegacion",
            "#viajesencoche",
            "#carretera",
            "#seguridadvial",
            "#movilidad",
        ),
    ),
    _copy(
        "Todo conductor debería probar estas herramientas",
        (
            "Conducir por una ciudad nueva o hacer muchos kilómetros por carretera "
            "exige algo más que conocer el destino. También necesitas reaccionar ante "
            "el tráfico, respetar las limitaciones, encontrar aparcamiento y saber dónde "
            "hacer una parada. Por eso hemos reunido cuatro aplicaciones que se "
            "complementan entre sí.\n\n"
            "RadarBot puede ayudarte con avisos de radares a lo largo de la ruta. ParkEz "
            "está pensada para localizar aparcamiento en la calle y reducir las vueltas "
            "al llegar. Waze ofrece información sobre la circulación y propone opciones "
            "cuando el recorrido habitual se complica. Google Maps permite navegar, "
            "preparar etapas y descubrir restaurantes, gasolineras, alojamientos, tiendas "
            "o lugares de ocio cercanos.\n\n"
            "La ventaja de esta selección está en que cada herramienta resuelve una parte "
            "diferente del trayecto. Para un desplazamiento corto quizá solo necesites "
            "revisar el tráfico y el parking; para un viaje largo puede interesarte "
            "preparar la ruta completa, las paradas y los servicios. Dedica un minuto a "
            "organizarlo todo antes de arrancar: activa el sonido de las indicaciones, "
            "coloca el teléfono de forma segura y evita tocarlo mientras conduces. Una "
            "app puede ahorrar tiempo, pero la prioridad sigue siendo llegar con "
            "seguridad. Comparte el vídeo con esa persona que siempre organiza los viajes "
            "y comenta cuál añadirías tú a la lista."
        ),
        (
            "#coches",
            "#conductores",
            "#appsparacoche",
            "#seguridadvial",
            "#trafico",
            "#parking",
            "#rutas",
            "#mapas",
            "#viajes",
            "#tecnologia",
            "#movilidad",
        ),
    ),
    _copy(
        "Tu próximo viaje empieza con estas 4 aplicaciones",
        (
            "Planificar bien un viaje en coche cambia por completo la experiencia. No "
            "es lo mismo salir sin referencias que conocer de antemano la mejor ruta, "
            "las posibles zonas de tráfico, dónde hacer una parada y qué opciones "
            "tendrás para aparcar al llegar. Estas cuatro aplicaciones forman un "
            "conjunto útil para cubrir todo ese recorrido.\n\n"
            "RadarBot está orientada a los avisos de radares, de modo que puedas "
            "mantenerte informado mientras prestas atención a la señalización y a los "
            "límites de cada vía. ParkEz ayuda con uno de los momentos más frustrantes "
            "del trayecto: encontrar aparcamiento en la calle cerca del destino. Waze "
            "permite consultar la circulación y considerar rutas alternativas cuando "
            "aparecen retenciones o incidencias. Google Maps funciona como base para "
            "organizar el itinerario y localizar gasolineras, restaurantes, hoteles, "
            "comercios, cines y otros puntos de interés.\n\n"
            "Puedes adaptar este kit a cada situación. En el día a día, Waze y ParkEz "
            "pueden ayudarte a reducir retrasos y vueltas innecesarias. En carretera, "
            "RadarBot y Google Maps aportan información para seguir el recorrido y "
            "preparar las paradas. Lo importante es configurar todo con el coche "
            "detenido, usar indicaciones por voz y no manipular el teléfono durante la "
            "conducción. También conviene descargar mapas si vas a atravesar zonas con "
            "poca cobertura y revisar que el soporte del móvil no limite la visibilidad.\n\n"
            "Guarda este carrusel antes de tu próxima escapada y envíaselo a tus "
            "acompañantes. Así todos pueden colaborar en la ruta sin convertir el viaje "
            "en una discusión sobre qué camino tomar."
        ),
        (
            "#coches",
            "#viajesencoche",
            "#appsparaconducir",
            "#carretera",
            "#trafico",
            "#aparcamiento",
            "#navegacion",
            "#conductores",
            "#seguridadvial",
            "#roadtrip",
            "#movilidad",
        ),
    ),
    _copy(
        "4 apps para tener cada parte del viaje bajo control",
        (
            "Un buen copiloto no solo indica dónde girar. También ayuda a anticipar lo "
            "que viene, propone alternativas, localiza una parada y evita que el final "
            "del trayecto se convierta en una búsqueda interminable de aparcamiento. Tu "
            "móvil puede cubrir muchas de esas tareas con cuatro aplicaciones bien "
            "elegidas.\n\n"
            "La primera es RadarBot, enfocada en los avisos de radares durante el "
            "recorrido. Puede resultar útil tanto en las carreteras habituales como en "
            "trayectos desconocidos, siempre como complemento de la señalización y de una "
            "conducción responsable. La segunda es ParkEz, una herramienta pensada para "
            "facilitar la búsqueda de aparcamiento en la calle. Cuando llegas a una zona "
            "concurrida, contar con una referencia puede evitar vueltas y retrasos.\n\n"
            "La tercera es Waze. Su enfoque en el estado del tráfico permite valorar si "
            "merece la pena mantener la ruta prevista o tomar una alternativa. La cuarta "
            "es Google Maps, que sirve para navegar y también para preparar paradas: "
            "puedes buscar restaurantes, gasolineras, hoteles, tiendas, cines o cualquier "
            "otro punto de interés próximo al camino.\n\n"
            "Juntas forman un kit muy completo, pero no hace falta utilizarlas todas al "
            "mismo tiempo. Antes de arrancar, piensa qué necesitas: avisos en carretera, "
            "información de tráfico, ayuda para aparcar o una planificación más amplia. "
            "Configura el destino mientras el vehículo está detenido, activa las "
            "instrucciones de voz y coloca el teléfono en un soporte que no interfiera "
            "con tu campo de visión.\n\n"
            "La tecnología puede ayudarte a ahorrar tiempo y conducir con menos estrés, "
            "pero la atención siempre debe permanecer en la vía. Guarda esta selección "
            "para el próximo viaje, compártela con otros conductores y dinos qué "
            "aplicación añadirías como quinta herramienta."
        ),
        (
            "#coches",
            "#conducir",
            "#appsutiles",
            "#appsparacoche",
            "#conductores",
            "#trafico",
            "#aparcamiento",
            "#rutas",
            "#googlemaps",
            "#waze",
            "#seguridadvial",
            "#carretera",
            "#viajes",
            "#movilidad",
            "#tecnologia",
        ),
    ),
)


CAR_TOOLS_SOCIAL_COPY_IDS: tuple[str, ...] = tuple(
    f"cartools-social-{index:02d}"
    for index in range(1, len(CAR_TOOLS_SOCIAL_COPIES) + 1)
)


def car_tools_social_copies() -> list[SocialCopy]:
    """Return independent copies so callers can safely format them."""
    return [
        SocialCopy(
            title=copy.title,
            description=copy.description,
            hashtags=list(copy.hashtags),
            hook=copy.hook,
        )
        for copy in CAR_TOOLS_SOCIAL_COPIES
    ]

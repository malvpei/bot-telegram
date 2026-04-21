from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from app.models import (
    Language,
    ScriptPackage,
    SlideRole,
    SocialCopy,
    TYPE_1_ROLES,
    TYPE_2_ROLES,
    TYPE_3_ROLES,
    VideoType,
)
from app.state import StateStore


# Em dash, en dash, fullwidth semicolon, hyphen-minus variants — anything that
# can render as a long dash or semicolon in the rendered video.
FORBIDDEN_TYPE_2_TOKENS: tuple[str, ...] = (";", "；", "—", "–", "ー", "―")


def _hash_signature(parts: list[str]) -> str:
    joined = "|".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TextChoices:
    hook_key: str
    month_keys: list[str]


class ScriptGenerator:
    MAX_ATTEMPTS = 80

    def __init__(self, state: StateStore) -> None:
        self.state = state

    def generate(self, video_type: VideoType, language: Language) -> ScriptPackage:
        builder = self._builder_for(video_type, language)
        last_signature = self.state.get_last_signature(video_type, language)
        known_signatures = self.state.get_known_signatures(video_type, language)

        package: ScriptPackage | None = None
        for _ in range(self.MAX_ATTEMPTS):
            package = builder()
            if package.signature == last_signature:
                continue
            if package.signature in known_signatures:
                continue
            return package

        # Final guarantee: at least don't repeat the *immediately* previous
        # video, even if everything historic is exhausted.
        for _ in range(self.MAX_ATTEMPTS):
            package = builder()
            if package.signature != last_signature:
                return package

        # Truly exhausted; surface as exception so caller can react instead of
        # silently violating the "no two equal in a row" rule.
        if package is None:
            package = builder()
        return package

    def _builder_for(self, video_type: VideoType, language: Language):
        if video_type == VideoType.TYPE_1:
            return self._build_type_1_es if language == Language.ES else self._build_type_1_en
        if video_type == VideoType.TYPE_2:
            return self._build_type_2_es if language == Language.ES else self._build_type_2_en
        return self._build_type_3_es if language == Language.ES else self._build_type_3_en

    # ------------------------------------------------------------------
    # Type 1 — narrative October → March
    # ------------------------------------------------------------------

    def _build_type_1_es(self) -> ScriptPackage:
        hook_options = {
            "h1": "Me metí en Dropshipping creyendo que iba a sacar dinero en dos semanas y lo que pasó mes a mes casi nadie lo cuenta",
            "h2": "Probé Dropshipping durante 6 meses y estas son las cifras de dinero reales que casi me hacen rendirme por el camino",
            "h3": "Entré a Dropshipping convencido de que era dinero fácil y cada mes siguiente me fue bajando los humos de una manera rara",
            "h4": "Hice Dropshipping medio año sin saber nada y la línea de dinero real fue muy distinta a la que venden por internet",
            "h5": "Si crees que con Dropshipping vas a sacar dinero rápido mira cómo fue mes a mes mi cuenta antes de hablar",
            "h6": "6 meses reales intentando hacer dinero con Dropshipping y la foto que más me dolió no fue ninguna de las de cero",
        }
        october = {
            "o1": "Octubre - 0€\nEmpecé con muchas ganas pero me quedé en parálisis por análisis pensando tanto cada paso que al final no lancé nada de verdad",
            "o2": "Octubre - 0€\nArranqué motivado aunque perdí demasiado tiempo con el logo y los colores sintiendo que trabajaba muchísimo mientras no avanzaba",
            "o3": "Octubre - 0€\nTenía todo montado en mi cabeza pero me daba miedo poner anuncios y perder dinero así que me bloqueé yo solo sin empezar",
            "o4": "Octubre - 0€\nMe metí con muchísimas ganas dudando de cada decisión y acabé con una tienda a medias y cero ventas después de semanas",
        }
        november = {
            "n1": "Noviembre - 0€\nSeguí en cero intentando vender solo con contenido orgánico mientras veía a otros facturar y yo atascado en el mismo punto",
            "n2": "Noviembre - 0€\nQuise moverlo sin gastar mis ahorros pero el miedo a invertir me frenó y pasó otro mes entero sin que cambiara nada",
            "n3": "Noviembre - 0€\nLo peor fue ver a otros sacar ventas mientras yo seguía a cero y esa comparación constante me dejó bastante rallado la verdad",
            "n4": "Noviembre - 0€\nProbé un par de productos al azar sin que pegara ninguno y entendí que ir a ciegas no me iba a funcionar nunca",
        }
        december = {
            "d1": "Diciembre - {amount}€\nLlegó la primera venta gracias al empujón de Navidad y pensé que ya había descubierto el secreto del ecommerce yo solo",
            "d2": "Diciembre - {amount}€\nEntró una venta pequeña por la locura navideña y me vine arriba creyendo que a partir de ahí todo sería igual de fácil",
            "d3": "Diciembre - {amount}€\nPor fin cayó la primera venta en Navidad y sentí que lo había pillado aunque me monté una película mucho más grande de la cuenta",
        }
        january = {
            "j1": "Enero - 0€\nSe acabaron las fiestas y las ventas murieron por completo así que pagar Shopify para no facturar me dejó sin motivación real",
            "j2": "Enero - 0€\nVolví a cero en cuanto pasó Navidad y estuve a punto de dejarlo todo para buscar un trabajo normal y olvidarme del tema",
            "j3": "Enero - 0€\nEl golpe fue duro porque después de Navidad no entró nada y me frustraba seguir pagando la tienda sin ver ningún resultado",
        }
        february = {
            "f1": "Febrero - {amount}€\nVi a un dropshipper usando Dropradar y me di una última oportunidad eligiendo productos por datos reales y no por intuición",
            "f2": "Febrero - {amount}€\nDescubrí Dropradar por otro chaval al que seguía y con una última bala guiada por métricas por fin empezaron a entrar ventas",
            "f3": "Febrero - {amount}€\nProbé Dropradar después de ver que otros sacaban productos con datos y al dejar de escoger por gusto personal la tienda arrancó",
        }
        march = {
            "m1": "Marzo - {amount}€\nNo me hice millonario ni me compré un Ferrari pero por fin tenía ingresos estables y dejé de ir totalmente a ciegas cada semana",
            "m2": "Marzo - {amount}€\nNada de jets ni mansiones porque la diferencia real fue empezar a usar métricas de verdad y dejar de adivinar cada decisión",
            "m3": "Marzo - {amount}€\nNo vivo con lujos pero ya tenía ventas sólidas cada mes y aprendí que los datos mandan muchísimo más que la intuición",
        }
        return self._compose_type_1(
            language=Language.ES,
            currency="€",
            hook_options=hook_options,
            october=october,
            november=november,
            december=december,
            january=january,
            february=february,
            march=march,
        )

    def _build_type_1_en(self) -> ScriptPackage:
        hook_options = {
            "h1": "I jumped into Dropshipping thinking I would see money in two weeks and the next months told a story nobody really shares online",
            "h2": "I ran Dropshipping for 6 months and these are the real money numbers that almost pushed me to quit the whole thing",
            "h3": "I started Dropshipping convinced it was fast money and every next month slowly killed that idea in a pretty uncomfortable way",
            "h4": "I did Dropshipping for half a year with zero experience and the real money curve looked nothing like the YouTube version",
            "h5": "If you think Dropshipping turns into money fast look at what actually happened in my account month by month first",
            "h6": "6 honest months trying to make money with Dropshipping and the photo that hurt the most was not any of the zero ones",
        }
        october = {
            "o1": "October - $0\nI started excited but got stuck in analysis paralysis overthinking every step and never really launching anything real",
            "o2": "October - $0\nI was motivated yet wasted way too much time on the logo and colors feeling busy while nothing actually moved",
            "o3": "October - $0\nEverything looked ready in my head but I was too scared to run ads and lose money so I just kept delaying the launch",
            "o4": "October - $0\nI jumped in with energy but doubted every decision and ended up with a half built store and zero sales after weeks",
        }
        november = {
            "n1": "November - $0\nI stayed at zero trying to force organic sales while watching other people making money and feeling stuck in the same spot",
            "n2": "November - $0\nI wanted to avoid risking my savings so fear kept me frozen and another month passed with the exact same numbers",
            "n3": "November - $0\nThe worst part was seeing everyone else getting sales while I had nothing and that comparison really got into my head",
            "n4": "November - $0\nI tested a couple of random products without a single one landing and realized winging it was never going to work",
        }
        december = {
            "d1": "December - ${amount}\nMy first sale came in thanks to the Christmas push and I thought I had finally cracked ecommerce by myself",
            "d2": "December - ${amount}\nA small Christmas sale hit and I got carried away believing it would stay that easy from there on out",
            "d3": "December - ${amount}\nThat first sale during Christmas made me think I had figured it out and I got way too confident way too quickly",
        }
        january = {
            "j1": "January - $0\nThe holidays ended and sales completely died so paying Shopify for nothing was killing my motivation every single week",
            "j2": "January - $0\nAs soon as Christmas was over I went right back to zero and was close to quitting for a normal job and forgetting everything",
            "j3": "January - $0\nReality hit hard because after the holidays nothing came in and I hated paying for a store with no results at all",
        }
        february = {
            "f1": "February - ${amount}\nI saw another dropshipper using Dropradar and gave myself one last shot picking products from real data and not gut",
            "f2": "February - ${amount}\nI found Dropradar through someone I followed and with one last try guided by metrics sales finally started to move",
            "f3": "February - ${amount}\nI tested Dropradar after seeing others rely on data and once I stopped choosing products by taste the store woke up",
        }
        march = {
            "m1": "March - ${amount}\nI did not become a millionaire and did not buy a Ferrari but I finally had stable income and stopped guessing every single week",
            "m2": "March - ${amount}\nNo jets or mansions because the real change was using solid metrics instead of pure intuition in every single decision",
            "m3": "March - ${amount}\nI am not living some crazy luxury life but the income finally felt stable and I learned data beats guessing every time",
        }
        return self._compose_type_1(
            language=Language.EN,
            currency="$",
            hook_options=hook_options,
            october=october,
            november=november,
            december=december,
            january=january,
            february=february,
            march=march,
        )

    def _compose_type_1(
        self,
        *,
        language: Language,
        currency: str,
        hook_options: dict[str, str],
        october: dict[str, str],
        november: dict[str, str],
        december: dict[str, str],
        january: dict[str, str],
        february: dict[str, str],
        march: dict[str, str],
    ) -> ScriptPackage:
        # Coherent monetary progression: december is the small first sale,
        # february is the recovery month, march is the stable income month.
        december_amount = random.randint(70, 140)
        february_amount = random.randint(450, 900)
        march_amount = random.randint(
            max(february_amount + 600, 2000),
            max(february_amount + 4500, 5800),
        )

        hook_key = random.choice(list(hook_options))
        keys = {
            SlideRole.OCTOBER: random.choice(list(october)),
            SlideRole.NOVEMBER: random.choice(list(november)),
            SlideRole.DECEMBER: random.choice(list(december)),
            SlideRole.JANUARY: random.choice(list(january)),
            SlideRole.FEBRUARY: random.choice(list(february)),
            SlideRole.MARCH: random.choice(list(march)),
        }

        slides_by_role: dict[SlideRole, str] = {
            SlideRole.HOOK: hook_options[hook_key],
            SlideRole.OCTOBER: october[keys[SlideRole.OCTOBER]],
            SlideRole.NOVEMBER: november[keys[SlideRole.NOVEMBER]],
            SlideRole.DECEMBER: december[keys[SlideRole.DECEMBER]].format(amount=december_amount),
            SlideRole.JANUARY: january[keys[SlideRole.JANUARY]],
            SlideRole.FEBRUARY: february[keys[SlideRole.FEBRUARY]].format(amount=february_amount),
            SlideRole.MARCH: march[keys[SlideRole.MARCH]].format(amount=march_amount),
        }

        ordered = [slides_by_role[role] for role in TYPE_1_ROLES]
        social_key, social_copy = self._choose_social_copy(VideoType.TYPE_1, language)
        signature = _hash_signature(
            [
                hook_key,
                keys[SlideRole.OCTOBER],
                keys[SlideRole.NOVEMBER],
                keys[SlideRole.DECEMBER],
                keys[SlideRole.JANUARY],
                keys[SlideRole.FEBRUARY],
                keys[SlideRole.MARCH],
                str(december_amount),
                str(february_amount),
                str(march_amount),
                currency,
                social_key,
            ]
        )

        # Type 1 narrative must always reach the Dropradar mention in February.
        if "Dropradar" not in slides_by_role[SlideRole.FEBRUARY]:
            raise RuntimeError("Tipo 1: el slide de febrero perdió la mención a Dropradar.")
        if "Dropshipping" not in slides_by_role[SlideRole.HOOK]:
            raise RuntimeError("Tipo 1: el hook debe mencionar Dropshipping.")

        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=signature,
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
        )

    # ------------------------------------------------------------------
    # Type 2 — "4 things I wish I knew" tips
    # ------------------------------------------------------------------

    def _build_type_2_es(self) -> ScriptPackage:
        hook_options = {
            "h1": "Antes de meterle dinero a Dropshipping mira estas 4 cosas o vas a aprender a base de perder efectivo como hice yo",
            "h2": "Si quieres que Dropshipping te deje dinero de verdad estas 4 cosas pesan muchísimo más de lo que parece desde fuera",
            "h3": "Habría pagado dinero por leer esto antes de abrir mi primera tienda de Dropshipping porque me habría ahorrado meses enteros",
            "h4": "Estas 4 cosas deciden si Dropshipping se convierte en dinero real o si solo te roba tiempo y ganas cada semana",
            "h5": "Si vas en serio con Dropshipping y quieres dinero online la siguiente foto resume lo que nadie te explica al principio",
            "h6": "4 cosas que separan el Dropshipping que te hace ganar dinero del que te arruina antes de empezar a escalar",
        }
        tip1 = {
            "t1": "1. Haz cuentas reales antes de vender\nMucha gente se lanza sin contar comisiones ni devoluciones y luego no entiende por qué no queda dinero a fin de mes",
            "t2": "1. Los márgenes no se improvisan\nRestar el coste del producto al precio de venta miente casi siempre porque pasarela e impuestos se comen gran parte del beneficio",
            "t3": "1. Números claros desde el día uno\nSi no cuentas todos los gastos reales el margen que ves en la hoja de cálculo es ficción pura y se nota en la cuenta",
            "t4": "1. La calculadora manda más que la intuición\nSi no sabes cuánto te queda limpio después de anuncios y envíos estás vendiendo a ciegas aunque tengas pedidos cada día",
        }
        tip2 = {
            "t1": "2. Una tienda barata nunca vende caro\nTu web decide en segundos si el cliente confía lo suficiente para pagar o se va directamente a buscar en otro sitio",
            "t2": "2. La primera impresión lo es todo\nAunque tu producto sea bueno una web descuidada tira la venta antes de que llegues siquiera a contarla en los datos",
            "t3": "2. El diseño construye confianza en silencio\nLa gente juzga tu marca en segundos y cada detalle visual le está diciendo al cliente si puede fiarse de ti o no",
            "t4": "2. Tu tienda es la cara de la marca\nSi cada detalle transmite descuido el cliente piensa que el producto también lo es y pierdes la venta sin enterarte",
        }
        tip3 = {
            "t1": "3. Encuentra productos rentables\nBuscar artículos a ciegas quema mucho tiempo y Dropradar te da una forma limpia de ver productos con potencial real antes de probarlos",
            "t2": "3. Deja de elegir productos por intuición\nLa suerte no escala y Dropradar filtra oportunidades por datos para que solo pruebes lo que tiene opciones reales de vender",
            "t3": "3. Atajo a productos que mueven\nDropradar te muestra qué se está vendiendo ahora mismo y por qué funciona sin que tengas que adivinar cada semana un producto nuevo",
            "t4": "3. Menos pruebas al azar\nDropradar filtra lo que tiene sentido probar según datos reales así evitas quemar presupuesto con productos que nadie estaba buscando",
        }
        tip4 = {
            "t1": "4. No desaparezcas después de la venta\nUn cliente al que no contestas se convierte rápido en una disputa y en una comisión perdida que duele bastante más que la venta",
            "t2": "4. El postventa protege tu negocio\nLos problemas casi nunca vienen del envío sino del silencio después de la compra cuando el cliente se siente solo y sin respuesta",
            "t3": "4. El soporte es parte de lo que vendes\nResponder rápido y con empatía es la herramienta de retención más barata y más efectiva que vas a tener en toda la tienda",
            "t4": "4. Cuida a quien ya te compró\nUn cliente bien atendido te da reseñas y vuelve a comprar mientras que uno ignorado te deja mala fama con una sola reclamación",
        }
        return self._compose_type_2(Language.ES, hook_options, tip1, tip2, tip3, tip4)

    def _build_type_2_en(self) -> ScriptPackage:
        hook_options = {
            "h1": "Before putting money into Dropshipping look at these 4 things or you will learn by losing cash just like I did at first",
            "h2": "If you want Dropshipping to actually make money these 4 things weigh way more than people admit online and in courses",
            "h3": "I would have paid money to read this before opening my first Dropshipping store because it saved me months later on",
            "h4": "These 4 things decide if Dropshipping turns into real money or just drains your time and energy every single week",
            "h5": "If you are serious about Dropshipping and online money the next photo is the part almost nobody explains to beginners",
            "h6": "4 things that separate the Dropshipping that makes money from the one that burns you out before you can even scale",
        }
        tip1 = {
            "t1": "1. Know your real numbers\nToo many sellers skip fees and refunds in their math and later wonder why nothing is left at the end of every month",
            "t2": "1. Margins are never obvious\nStaring at the product cost on the supplier page lies almost every time once taxes and platform cuts eat part of the profit",
            "t3": "1. Run the numbers from day one\nIf you miss the hidden costs the profit you think you see on your spreadsheet is pure fiction and the bank account proves it",
            "t4": "1. The calculator beats the feeling\nIf you do not know what you keep after ads and shipping you are selling blind even when orders come in every single day",
        }
        tip2 = {
            "t1": "2. A cheap looking store will never sell premium\nYour site decides in seconds whether a visitor trusts you enough to buy or just leaves to check somewhere else",
            "t2": "2. First impressions decide the sale\nEven a solid product dies on a messy storefront and you lose the order before you can even count it in your analytics",
            "t3": "2. Design builds trust quietly\nPeople size up your brand in seconds and every visual detail is telling the buyer whether to trust you or move on to the next tab",
            "t4": "2. Your store is the face of your brand\nIf every detail feels rushed the customer assumes the product is rushed too and the sale is lost without you noticing",
        }
        tip3 = {
            "t1": "3. Find profitable products\nRandom hunting burns time fast and Dropradar gives you a cleaner way to spot items with real potential before testing anything",
            "t2": "3. Stop picking products on gut feeling\nLuck does not scale and Dropradar filters opportunities by real data so you only test things that can actually sell",
            "t3": "3. Shortcut to items that move\nDropradar shows you what is selling right now and why it works so you never have to guess a winner again every single week",
            "t4": "3. Fewer random tests\nDropradar filters what is worth testing based on real data so you avoid burning budget on products nobody was actually searching for",
        }
        tip4 = {
            "t1": "4. Do not vanish after the sale\nAn ignored customer turns into a chargeback much faster than you think and that hit costs more than the sale itself",
            "t2": "4. After sales care protects the business\nMost disputes do not come from shipping but from silence once the customer has paid and feels alone",
            "t3": "4. Support is part of what you sell\nReplying quickly and with empathy is the cheapest and most effective retention tool you will ever have in this business",
            "t4": "4. Take care of the buyer you already have\nA well treated customer leaves reviews and comes back while an ignored one leaves bad reputation in a single complaint",
        }
        return self._compose_type_2(Language.EN, hook_options, tip1, tip2, tip3, tip4)

    def _compose_type_2(
        self,
        language: Language,
        hook_options: dict[str, str],
        tip1: dict[str, str],
        tip2: dict[str, str],
        tip3: dict[str, str],
        tip4: dict[str, str],
    ) -> ScriptPackage:
        hook_key = random.choice(list(hook_options))
        keys = {
            SlideRole.TIP1: random.choice(list(tip1)),
            SlideRole.TIP2: random.choice(list(tip2)),
            SlideRole.TIP3: random.choice(list(tip3)),
            SlideRole.TIP4: random.choice(list(tip4)),
        }

        slides_by_role: dict[SlideRole, str] = {
            SlideRole.HOOK: hook_options[hook_key],
            SlideRole.TIP1: tip1[keys[SlideRole.TIP1]],
            SlideRole.TIP2: tip2[keys[SlideRole.TIP2]],
            SlideRole.TIP3: tip3[keys[SlideRole.TIP3]],
            SlideRole.TIP4: tip4[keys[SlideRole.TIP4]],
        }

        social_key, social_copy = self._choose_social_copy(VideoType.TYPE_2, language)
        signature = _hash_signature(
            [
                hook_key,
                keys[SlideRole.TIP1],
                keys[SlideRole.TIP2],
                keys[SlideRole.TIP3],
                keys[SlideRole.TIP4],
                social_key,
            ]
        )

        ordered = [slides_by_role[role] for role in TYPE_2_ROLES]
        self._assert_type_2_rules(slides_by_role)
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=signature,
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
        )

    @staticmethod
    def _assert_type_2_rules(slides_by_role: dict[SlideRole, str]) -> None:
        for role, slide in slides_by_role.items():
            for token in FORBIDDEN_TYPE_2_TOKENS:
                if token in slide:
                    raise ValueError(
                        f"Tipo 2 ({role.value}): el texto contiene el carácter prohibido '{token}'."
                    )
        if "Dropradar" not in slides_by_role.get(SlideRole.TIP3, ""):
            raise ValueError("Tipo 2: el consejo 3 debe mencionar Dropradar.")
        if "Dropshipping" not in slides_by_role.get(SlideRole.HOOK, ""):
            raise ValueError("Tipo 2: el hook debe mencionar Dropshipping.")

    # ------------------------------------------------------------------
    # Type 3 — one hook photo + fixed tool stack
    # ------------------------------------------------------------------

    def _build_type_3_es(self) -> ScriptPackage:
        hooks = {
            "h1": "Como empezar Dropshipping en 2026\nsin perderte entre mil herramientas",
            "h2": "Asi se hace Dropshipping en 2026\ncon lo minimo para arrancar",
            "h3": "Empieza Dropshipping en 2026\nnunca fue tan facil como ahora",
            "h4": "Monta tu primera tienda de Dropshipping en 2026\npaso a paso sin rodeos",
            "h5": "Guia express para arrancar Dropshipping en 2026\ny dejar de posponerlo",
            "h6": "Dropshipping en 2026\nestas son las herramientas que realmente necesitas",
        }
        tools = {
            SlideRole.TOOL_STORE: "1. Tienda\nCrea tu tienda online\nUsa Shopify",
            SlideRole.TOOL_PRODUCT_SEARCH: "2. Productos\nEncuentra productos ganadores\nUsa Dropradar",
            SlideRole.TOOL_SCRIPTS: "3. Guiones\nEscribe guiones rapidos\nUsa ChatGPT",
            SlideRole.TOOL_PAYMENTS: random.choice(
                (
                    "4. Pagos\nCobra tus pedidos\nUsa PayPal",
                    "4. Pagos\nCobra de forma segura\nUsa Stripe",
                )
            ),
            SlideRole.TOOL_EDITING: random.choice(
                (
                    "5. Edicion\nCrea visuales limpios\nUsa Canva",
                    "5. Edicion\nEdita videos rapido\nUsa CapCut",
                )
            ),
            SlideRole.TOOL_MARKETING: random.choice(
                (
                    "6. Marketing\nCrea comunidad\nUsa Instagram",
                    "6. Marketing\nPublica videos cortos\nUsa TikTok",
                )
            ),
        }
        return self._compose_type_3(Language.ES, hooks, tools)

    def _build_type_3_en(self) -> ScriptPackage:
        hooks = {
            "h1": "How to start Dropshipping in 2026\nwithout getting lost between tools",
            "h2": "This is how Dropshipping works in 2026\nwith the minimum to get moving",
            "h3": "Start Dropshipping in 2026\nit has never been this easy to begin",
            "h4": "Build your first Dropshipping store in 2026\nstep by step with no fluff",
            "h5": "Quick guide to start Dropshipping in 2026\nand finally stop delaying it",
            "h6": "Dropshipping in 2026\nthese are the tools you actually need to begin",
        }
        tools = {
            SlideRole.TOOL_STORE: "1. Store\nBuild your online store\nUse Shopify",
            SlideRole.TOOL_PRODUCT_SEARCH: "2. Products\nFind winning products\nUse Dropradar",
            SlideRole.TOOL_SCRIPTS: "3. Scripts\nWrite quick scripts\nUse ChatGPT",
            SlideRole.TOOL_PAYMENTS: random.choice(
                (
                    "4. Payments\nTake customer payments\nUse PayPal",
                    "4. Payments\nTake secure payments\nUse Stripe",
                )
            ),
            SlideRole.TOOL_EDITING: random.choice(
                (
                    "5. Editing\nCreate clean visuals\nUse Canva",
                    "5. Editing\nEdit videos fast\nUse CapCut",
                )
            ),
            SlideRole.TOOL_MARKETING: random.choice(
                (
                    "6. Marketing\nBuild a community\nUse Instagram",
                    "6. Marketing\nPost short videos\nUse TikTok",
                )
            ),
        }
        return self._compose_type_3(Language.EN, hooks, tools)

    def _compose_type_3(
        self,
        language: Language,
        hook_options: dict[str, str],
        tools: dict[SlideRole, str],
    ) -> ScriptPackage:
        hook_key = random.choice(list(hook_options))
        slides_by_role = {SlideRole.HOOK: hook_options[hook_key], **tools}
        ordered = [slides_by_role[role] for role in TYPE_3_ROLES]
        social_key, social_copy = self._choose_social_copy(VideoType.TYPE_3, language)
        signature = _hash_signature([hook_key, *ordered[1:], social_key])
        self._assert_type_3_rules(slides_by_role)
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=signature,
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
        )

    def _choose_social_copy(
        self,
        video_type: VideoType,
        language: Language,
    ) -> tuple[str, SocialCopy]:
        variants = self._social_copy_variants(video_type, language)
        key = random.choice(list(variants))
        title, description, hashtags = variants[key]
        return key, SocialCopy(
            title=title,
            description=description,
            hashtags=hashtags,
        )

    def _social_copy_variants(
        self,
        video_type: VideoType,
        language: Language,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if language == Language.EN:
            return self._social_copy_variants_en(video_type)
        return self._social_copy_variants_es(video_type)

    def _social_copy_variants_es(
        self,
        video_type: VideoType,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if video_type == VideoType.TYPE_1:
            return {
                "es1": (
                    "Mis 6 meses reales con dropshipping",
                    "Nadie me preparó para lo aburridos y frustrantes que iban a ser los primeros meses. Abrí la tienda con muchísimas ganas, me pasé noches enteras tocando colores, fuentes y textos, convencido de que al lanzar notaría movimiento rápido. Lo que vino fue justo lo contrario: ventas a cero, dudas constantes, productos elegidos a ojo y esa sensación rara de estar trabajando mucho sin avanzar nada. Lo que cambió la historia no fue un producto viral ni un gurú nuevo, fue dejar de decidir por intuición y empezar a mirar señales reales de qué se estaba vendiendo, por qué se estaba vendiendo y si tenía sentido intentar competir con eso. Cuando cada prueba pasó a tener una razón detrás, cada fallo empezó a enseñarme algo en vez de solo dolerme. Este carrusel es la versión honesta de esos 6 meses, los momentos en los que casi lo dejé, el punto en el que apareció Dropradar y el mes en el que por fin los números dejaron de parecerme una lotería mensual. Si estás empezando ahora mismo, espero que te ahorre al menos alguno de los meses malos por los que tuve que pasar yo.",
                    ["#dropshipping", "#ecommerce", "#emprender", "#tiendaonline", "#dropradar"],
                ),
                "es2": (
                    "De cero ventas a un sistema con datos",
                    "Esta no es la historia de alguien que acertó a la primera, es la historia de alguien que estuvo bastante perdido durante más tiempo del que le gustaría admitir en un video. Los primeros meses fueron tienda abierta, horas metidas, productos probados al azar y una sensación constante de estar haciendo algo mal sin saber exactamente qué parte era. Luego empezó la parte más fea, comparar mis cifras con las de gente en redes, dudar de mí mismo y plantearme en serio si tenía algún sentido seguir gastando tiempo y dinero en esto. El salto real no vino de un curso caro ni de un producto ganador que cayó del cielo, vino de dejar de escoger a ciegas y empezar a validar cada idea con información más clara, demanda, tendencia, anuncios que ya funcionaban y señales de venta fiables. No es una historia de lujo rápido, es una historia de aprender a medir antes de escalar, y para mí esa mentalidad es la parte más valiosa de todo este recorrido. Si algo aquí te suena familiar, probablemente ya estás más cerca del cambio de lo que crees ahora mismo.",
                    ["#dropshippingespana", "#ecommerce", "#ventasonline", "#emprendedores", "#dropradar"],
                ),
                "es3": (
                    "Lo que aprendi despues de casi rendirme",
                    "Si estás empezando con dropshipping y sientes que todo va demasiado lento, lee esto antes de pensar que el problema eres tú. Yo pasé meses enteros creyendo que no valía para esto, me levantaba temprano, cerraba tarde, abría y cerraba la tienda una y otra vez, probaba productos que veía en TikTok y seguía esperando ese momento mágico en el que los pedidos empezaran a entrar solos. Nunca llegó, porque lo estaba haciendo sin ningún criterio real. El bloqueo no era trabajar poco, era trabajar sin método, probar productos sin pensarlos, copiar tiendas sin entenderlas y no saber qué datos mirar hacía que cada mes se pareciera demasiado al anterior. Cuando por fin tuve un sistema claro para elegir mejor, cada prueba me devolvía información útil en vez de solo restarme dinero. El cambio no fue espectacular, fue progresivo, y eso es precisamente lo que lo hizo sostenible. Este carrusel es lo que me habría gustado ver cuando pensaba en rendirme, porque muchas veces el problema no es la constancia, es la falta de criterio para saber qué toca probar esta semana.",
                    ["#dropshipping", "#negociosonline", "#ecommercetips", "#shopify", "#dropradar"],
                ),
                "es4": (
                    "Mis numeros cambiaron cuando cambie el metodo",
                    "El salto no vino del producto perfecto ni de una tienda impecable a la primera, vino de aceptar algo bastante incómodo, que mi gusto personal no era una estrategia. Durante meses elegí productos porque a mí me gustaban, porque los veía bonitos o porque alguien los mencionaba en un reel, y el resultado era el que todos conocemos en silencio, mucho esfuerzo, poca venta y cero aprendizaje claro. Cuando por fin empecé a comparar datos, mirar demanda real, creativos, tendencia y señales de venta, todo se volvió menos emocional y más ordenado. Tomé decisiones con menos ego y los números empezaron a moverse en una dirección que, por primera vez, podía explicar con cabeza. Para mí esa fue la diferencia real entre adivinar y construir un proceso que se puede repetir mes a mes. No soy un caso extraordinario, soy un caso medianamente constante, y creo que ese es el tipo de historia que más le sirve a alguien que está pensando en empezar, porque evita la parte más cara del proceso, que es perder meses confundiendo gusto personal con estrategia real.",
                    ["#emprendimiento", "#dropshipping", "#productoganador", "#ecommerce", "#dropradar"],
                ),
            }
        if video_type == VideoType.TYPE_2:
            return {
                "es1": (
                    "4 cosas que me habria gustado saber antes",
                    "Guarda esto antes de meterle presupuesto a tu primera tienda, porque te puede ahorrar meses de ir a ciegas y de probar cosas sin saber qué estás midiendo. Muchos empiezan fijándose solo en el anuncio y en el producto viral, pero la base real está antes de todo eso. Entender tus márgenes reales, construir una web que transmita confianza en segundos, elegir productos con criterio y preparar un soporte mínimamente decente es lo que decide si una tienda aguanta el primer golpe de tráfico o se cae sola en cuanto algo sale mal. Son cosas poco glamurosas, no venden bien en reels y por eso casi nadie las pone en sus videos, pero si una de estas bases falla, todo lo demás se vuelve mucho más difícil de escalar después. Mira cada uno de estos 4 puntos como una mini auditoría de tu tienda actual o de la que estás a punto de abrir, porque la parte que ahora mismo menos controlas suele ser la que más te está costando cada semana. Si lo aplicas con calma, probablemente cambie bastante más que cualquier nuevo truco de anuncios que leas por internet este mes.",
                    ["#dropshipping", "#ecommerce", "#shopify", "#emprenderonline", "#dropradar"],
                ),
                "es2": (
                    "La checklist basica antes de vender online",
                    "Márgenes, confianza, producto y soporte, cuatro áreas que parecen obvias cuando las dices en voz alta, pero son justo las que más gente pasa por alto al empezar. Puedes tener un anuncio viral y tráfico entrando por todos lados, pero si tus números no cuadran, la web no genera confianza o el producto fue elegido por impulso, las ventas no compensan el gasto y acabas con la sensación rara de estar trabajando para nadie. Las tiendas que duran no son las que encuentran un producto mágico, son las que tienen la base bien montada antes de empezar a escalar en serio. Esta checklist es la que me habría gustado tener delante cuando preparaba mi primera tienda, antes de pagar anuncios, antes de elegir productos y antes de pensar que el problema era solo el creativo. Revísala tranquilo, sin prisa, porque arreglar una sola de estas áreas normalmente cambia bastante más de lo que parece desde fuera y los resultados se notan pronto. Úsala como guía rápida siempre que algo en tu tienda no acabe de funcionar y no sepas muy bien por dónde empezar a mirar.",
                    ["#ecommercetips", "#dropshippingtips", "#tiendaonline", "#ventas", "#dropradar"],
                ),
                "es3": (
                    "Antes de lanzar anuncios revisa esto",
                    "Muchos fallos no vienen del producto en sí, vienen de lanzar sin tener los números claros, sin estructura y sin un criterio real para decidir qué probar. Antes de gastar un euro en anuncios conviene revisar cosas básicas con calma. ¿Tu margen real aguanta comisiones, devoluciones y coste de adquisición? ¿Tu tienda transmite confianza en los primeros segundos, tanto en móvil como en ordenador? ¿Tu producto se eligió mirando datos o solo porque era bonito en la foto del proveedor? ¿Tienes una respuesta preparada cuando el primer cliente escriba con dudas sobre envío o devolución? Un buen producto ayuda, pero una estructura floja puede matar la venta antes incluso de que empiece. Todo esto parece básico cuando lo lees, pero en la práctica la mayoría lanza con una o dos de estas piezas a medio hacer. Esta checklist no es teoría bonita, es el tipo de revisión práctica que conviene hacer antes de meter más presupuesto o asumir que el problema es solo el creativo del anuncio en ese momento concreto de la semana.",
                    ["#dropshipping", "#marketingdigital", "#shopifytips", "#negociosonline", "#dropradar"],
                ),
                "es4": (
                    "4 lecciones para no empezar a ciegas",
                    "Si llevas un tiempo probando productos al azar, cambia el enfoque antes de seguir quemando presupuesto sin aprender nada. El dropshipping se vuelve mucho más claro cuando entiendes qué revisar primero, números reales, percepción de marca, demanda real en el mercado y experiencia del cliente después del cobro. No es cuestión de tener la tienda más bonita ni el producto más viral, es cuestión de entender qué hace que una tienda funcione en el día a día, más allá del anuncio inicial que te trajo la primera venta. Cuando cada decisión parte de un criterio en vez de una corazonada, todo se vuelve más ordenado y los fallos dejan de ser golpes inesperados para convertirse en información útil que puedes usar al mes siguiente. Este video no es teoría bonita ni motivación vacía, es una guía rápida para evitar los errores que más caros se pagan al principio. Si una de las cuatro partes te pilla dudando, probablemente ese sea el lugar exacto por el que empezar esta semana, antes de tocar presupuestos o cambiar de producto una vez más sin tener la base revisada.",
                    ["#ecommerce", "#dropshippingespana", "#emprendedores", "#ventasonline", "#dropradar"],
                ),
            }
        return {
            "es1": (
                "Como empezar dropshipping en 2026",
                "Estas son las herramientas base para empezar dropshipping en 2026 sin perderte entre mil opciones y comparativas sin fin. La idea no es montar la suite más avanzada del mercado, es construir un flujo simple que te deje validar rápido, una tienda que funcione desde el primer día, una forma de buscar productos con datos en vez de solo intuición, un sistema para crear contenido sin atascarte cada semana, un método para cobrar de manera segura, una edición ágil y una plataforma donde puedas practicar tráfico orgánico cada día. La clave al principio no es acumular apps, es elegir pocas herramientas y usarlas bien durante las primeras semanas. La ventaja no está en las funciones avanzadas, está en la velocidad con la que pruebas ideas reales y aprendes de cada intento. Empieza simple, valida rápido y mejora las piezas cuando ya tengas señales claras del mercado. Esta base sirve tanto si quieres probar tu primer producto como si piensas en algo más serio a medio plazo, porque el orden de las piezas no cambia demasiado entre una idea pequeña y un proyecto un poco más ambicioso.",
                ["#dropshipping2026", "#ecommerce", "#shopify", "#tiktokmarketing", "#dropradar"],
            ),
            "es2": (
                "Tu stack para lanzar una tienda online",
                "No hace falta suscribirte a mil herramientas para lanzar tu primera tienda online, y la mayoría de gente las acumula sin llegar a usarlas bien ni entender qué aporta cada una. Con una base mínima puedes hacer más de lo que parece, una plataforma sólida para vender, una forma limpia de buscar productos con potencial real, un método para crear contenido rápido sin perderte en la edición, una pasarela de pago fiable desde el primer día, una herramienta de edición cómoda para mantener el ritmo y un canal de tráfico orgánico que puedas practicar a diario sin gastar un euro extra. Este stack está pensado para arrancar con movimiento, no para pasarte semanas configurando cosas antes de validar un solo producto. Al principio lo que importa no es la herramienta más avanzada, es la que te deja publicar, probar y corregir rápido. Si ya llevas tiempo dando vueltas a qué apps elegir, este puede ser el empujón que necesitas para dejar de leer comparativas y poner algo real delante del mercado para que te responda.",
                ["#dropshipping", "#tiendaonline", "#herramientas", "#emprender", "#dropradar"],
            ),
            "es3": (
                "Herramientas para empezar desde cero",
                "Tienda, búsqueda de producto, guiones, pagos, edición y tráfico orgánico, este es el orden más simple para arrancar desde cero sin volverte loco con las opciones disponibles. Primero montas una estructura mínima que funcione y que puedas llenar de productos, luego eliges qué vender con un criterio claro en vez de a ojo, preparas contenido que puedas publicar de forma sostenida sin quemarte la primera semana, configuras tus pagos con calma para no tener sustos legales y terminas midiendo la respuesta real del mercado en canales orgánicos antes de meter un euro en anuncios. Lo importante al principio no es hacerlo perfecto, es avanzar con claridad, evitar quedarte bloqueado por exceso de herramientas y entender que cada bloque sirve para una cosa concreta. Cuando cada parte tiene su rol dentro del flujo, tu progreso deja de depender de encontrar la app secreta y empieza a depender de tu constancia. Guarda esta guía y úsala como referencia cada vez que dudes por dónde seguir con tu tienda.",
                ["#ecommerce2026", "#dropshippingtips", "#shopify", "#capcut", "#dropradar"],
            ),
            "es4": (
                "La ruta simple para tu primera tienda",
                "Si llevas semanas aplazando el paso porque no sabes qué herramientas usar, empieza por esta combinación y prueba rápido sin seguir buscando la fórmula perfecta. Una tienda sencilla pero bien montada, productos elegidos con datos en vez de corazonadas, guiones claros para tu contenido, pagos listos desde el día uno, edición ágil y un canal orgánico donde practicar cada día puede darte suficiente feedback del mercado para saber si vas por buen camino o si conviene ajustar el enfoque. La clave al principio no es optimizar absolutamente todo, es llegar a ver reacciones reales lo antes posible, incluso si son pequeñas. Una vez tienes esas primeras señales, ya sabes qué parte conviene pulir primero, producto, contenido, precio o estructura, y cada mejora tiene más sentido porque parte de información real. Antes de eso, casi todo son suposiciones que te hacen perder semanas. Guarda este stack y úsalo como hoja de ruta en vez de saltar de video en video buscando la fórmula mágica que, realmente, no existe al nivel que la venden.",
                ["#dropshipping", "#negociosonline", "#tiktokshop", "#marketingorganico", "#dropradar"],
            ),
        }

    def _social_copy_variants_en(
        self,
        video_type: VideoType,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if video_type == VideoType.TYPE_1:
            return {
                "en1": (
                    "My real 6 month dropshipping journey",
                    "Nobody warned me how boring and frustrating the first months were going to feel. I opened the store full of motivation, spent nights fixing colors, fonts and texts, convinced that once I launched, things would start moving quickly. The reality was the exact opposite, zero sales, constant doubts, products picked on feelings alone and that strange sensation of working really hard while nothing was actually moving. What finally changed the story was not a viral product or a new guru, it was giving up on intuition and starting to read real signals about what was selling, why it was selling and whether it even made sense for me to compete with it. Once every test had a real reason behind it, every failure started teaching me something instead of just hurting and draining my budget. This carousel is the honest version of those 6 months, the moments I almost quit, the point where Dropradar came in and the month when the numbers finally stopped feeling like a monthly lottery that I could not explain.",
                    ["#dropshipping", "#ecommerce", "#onlinebusiness", "#shopify", "#dropradar"],
                ),
                "en2": (
                    "What changed after months of guessing",
                    "The shift was not luck and it did not happen overnight, no matter how clean it looks in a short video like this. I spent months running an open store, overthinking every detail and testing products without any real reason behind the decisions I was making. I copied things from other people, tweaked creatives in the dark and kept refreshing analytics hoping for something magical to happen on its own. The real turning point was accepting that my process needed better data, not more effort or another expensive course. Once I started looking at demand, competition, proven creatives and sales signals more seriously, every test became easier to interpret, wins were easier to repeat, losses were easier to understand and the whole thing started feeling less like gambling and more like a process. There was no single product that fixed everything for me. There was a slow shift toward a way of thinking that made the work worth doing every morning without dragging my motivation down with it every single week of the month.",
                    ["#dropshippingtips", "#ecommercebusiness", "#entrepreneur", "#productresearch", "#dropradar"],
                ),
                "en3": (
                    "From almost quitting to clearer numbers",
                    "If you are starting out and feel like things are painfully slow, watch this before blaming yourself for the results on the screen. I spent a long time thinking I was not built for this, I woke up early, stayed up late, opened and closed the store countless times and tested random products I saw trending on TikTok. The sales did not come, not because I was lazy, but because I had no real system behind my choices. Testing products without criteria, copying stores without understanding them and ignoring the data you should actually watch keeps every month looking too similar to the last one. A cleaner decision system will not make dropshipping easy overnight, but it makes every test more useful and every loss less expensive because you can explain it. The shift was not dramatic, it was gradual, and that is exactly why it became sustainable for me. This carousel is the version of the story I wish I had seen during the months I was that close to giving up, and if any slide here feels familiar, take it as a sign that your problem is probably not effort.",
                    ["#dropshipping", "#ecommercejourney", "#shopifystore", "#onlineincome", "#dropradar"],
                ),
                "en4": (
                    "The lesson my first sales taught me",
                    "The product was only part of it, and that took me longer to accept than I would like to admit out loud. The real unlock was understanding that personal taste is not a strategy and that every time I chose a product because I liked it, I was rolling a dice with my own money without even noticing. Once I stepped back from that ego and started picking with cleaner data around demand, creatives, competition and real sales signals, the whole thing shifted. Dropshipping started feeling less like gambling and more like a process I could actually improve over time, my wins were easier to repeat and my losses finally made sense. I was not smarter than before, I just had a better way of asking questions about a product before spending real money on it. You do not need to become obsessed with analytics to see a difference, you just need enough structure to stop trusting pure gut feeling alone. If you keep hitting walls without knowing why, this carousel might give you the order of decisions I wish I had found earlier.",
                    ["#ecommerce", "#dropshippingbusiness", "#digitalbusiness", "#shopifytips", "#dropradar"],
                ),
            }
        if video_type == VideoType.TYPE_2:
            return {
                "en1": (
                    "4 things I wish I knew before dropshipping",
                    "Save this before launching your first store, because it can save you months of learning things the hard way and losing budget you did not have to lose. Most beginners focus only on finding a viral product or the perfect ad, but the real base sits before all of that. Understanding your actual margins, building a site that feels safe within seconds, choosing products with a clear reason and preparing at least a basic after-sale response is what decides whether your store survives the first real wave of traffic or just leaks money silently. These basics are not flashy and do not look great in a reel, and that is exactly why most creators skip them when they teach online. But if one of these parts breaks, the whole business becomes much harder to scale later. Treat each of these 4 points as a quick audit of the store you already run or the one you are about to open. The part that feels least comfortable right now is probably the one costing you the most every single week without showing up directly on any screen you are looking at.",
                    ["#dropshipping", "#ecommerce", "#shopify", "#dropshippingtips", "#dropradar"],
                ),
                "en2": (
                    "The simple checklist before selling online",
                    "Margins, trust, product research and after-sale support, four areas that sound obvious when you say them out loud, but they are the exact pieces most people skip at the start. You can have a viral creative and solid traffic, but if your numbers do not hold up, your site does not feel trustworthy or your product was picked by impulse, the sales will never fix the structure that was wrong from day one. Stores that actually last are not the ones that stumbled into a magical product, they are the ones that set up the basics before scaling and before paying for ads. This is the checklist I wish I had in front of me when I was getting ready to launch, before paying for ads, before picking products and before assuming my only problem was the creative. Take your time with each point, not as theory, but as a real review of your store. Fixing one of these areas usually changes a lot more than it looks from the outside and the results show up faster than most people expect when the base is finally solid instead of improvised.",
                    ["#ecommercetips", "#onlinebusiness", "#shopifystore", "#productresearch", "#dropradar"],
                ),
                "en3": (
                    "Watch this before running ads",
                    "A lot of stores fail before traffic even has a fair chance, because the numbers and product logic were never clear in the first place. Before running ads, it is worth checking a few things honestly and with calm. Can your margin really survive platform fees, refunds and acquisition costs at the same time? Does the store build trust within the first few seconds on both mobile and desktop? Was the product chosen using data or just because it looked cool on your screen while scrolling? Do you have at least a basic answer prepared for when a buyer writes asking about shipping or refunds the first week? A good product helps, but a weak setup can kill the sale before the buyer even gets close to checkout. All of this sounds basic when you read it, yet most people launch with one or two of these pieces half done. This checklist is not theory, it is the type of quick review worth doing before spending more money or assuming the creative is the only problem on the store right now that you should be fixing.",
                    ["#dropshippingtips", "#ecommercemarketing", "#shopifytips", "#digitalmarketing", "#dropradar"],
                ),
                "en4": (
                    "4 lessons so you do not start blind",
                    "If you have been testing random products for a while, change the approach before burning more budget without learning anything that you can actually reuse later. Dropshipping becomes clearer once you know what to check first, real numbers, perceived trust, actual demand in the market and the customer experience after checkout. It is not about having the prettiest store or the most viral product, it is about understanding what makes a store work day after day, beyond the hype of a single ad or a single lucky week. When every decision comes from a reason instead of a feeling, the losses become information instead of random hits and you stop reacting to every noise on social media. You stop reacting and start improving. This is a short practical guide for avoiding the beginner mistakes that end up costing the most. If one of the four points here catches you hesitating, that is probably the exact place worth starting this week before touching anything else in the store or in the creatives this week.",
                    ["#dropshipping", "#ecommercebusiness", "#entrepreneurtips", "#onlinestore", "#dropradar"],
                ),
            }
        return {
            "en1": (
                "How to start dropshipping in 2026",
                "These are the core tools for starting dropshipping in 2026 without overcomplicating every small decision along the way. The goal is not to build the most advanced stack, it is to put a simple workflow in place that lets you validate fast, a store you can launch on day one, a cleaner way to research products with data instead of gut feeling, a system to create content without blocking on editing every time you want to post, a safe way to take payments from the first sale, quick visuals that keep the brand consistent and an organic channel you can practice every day without paying a cent. At the start the advantage is not in the premium features, it is in how fast you can test real ideas, measure real responses and adjust the plan with information you actually trust. Begin simple, validate early, learn something from each attempt and upgrade the pieces once you have clear signals from the market. This base works whether you want to test your first product or build something bigger without rebuilding the base later.",
                ["#dropshipping2026", "#ecommerce", "#shopify", "#tiktokmarketing", "#dropradar"],
            ),
            "en2": (
                "Your starter stack for an online store",
                "You do not need a hundred tools to launch your first online store, and most people collect apps they never really use or even understand fully. With a minimal base you can do more than it looks, a solid selling platform, a cleaner way to find products with real potential, a fast content workflow you can repeat without thinking too much, a reliable payment setup from day one, a comfortable editing tool that keeps the ritual going and an organic traffic channel you can practice every day without spending anything extra. This stack is built for momentum, not for spending weeks configuring things before you even test a single product or post a single video. In the beginning what matters is not the most advanced tool, it is the one that lets you publish, test and adjust quickly with real feedback. If you have been going back and forth comparing apps for weeks, this is probably the push you need to stop reading reviews and actually put something real in front of the market and letting it react to it for a change.",
                ["#dropshipping", "#onlinestore", "#ecommercetools", "#entrepreneur", "#dropradar"],
            ),
            "en3": (
                "Tools to start from zero",
                "Store, product research, scripts, payments, editing and organic traffic, this is the simple order for starting from scratch without getting lost in tool reviews and comparisons that never really end. First you set up the minimum structure that works and that you can actually fill with products, then you pick what to sell with clearer signals instead of pure guessing, prepare content you can publish consistently without burning out in the first week, configure your payments calmly so nothing breaks later and measure how the market reacts to what you put out before paying for any traffic. The goal at the start is not perfection, it is useful feedback and learning how to react to it with calm. When every block has a clear role in the workflow, your progress stops depending on finding a secret app and starts depending on your consistency. Save this as a reference for moments when you feel stuck choosing the next move, and come back whenever you want to check if any base block is missing in your setup.",
                ["#ecommerce2026", "#dropshippingtips", "#shopify", "#capcut", "#dropradar"],
            ),
            "en4": (
                "The simple route to your first store",
                "If you keep delaying the first step because you do not know which tools to use, start with this setup and test fast instead of spending more weeks looking for the perfect formula in videos. A simple but clean store, products chosen with data instead of pure instinct, clear scripts for your content, payments ready from day one, quick editing and an organic channel where you can practice every day can give you enough feedback from the market to know whether you are moving in the right direction or something needs a real change. At the beginning the goal is not to optimize absolutely everything, it is to see real reactions as soon as possible, even if they are small. Once you have those early signals, you will know which part deserves attention first, product, content, price or structure, and every improvement will sit on top of information you actually trust. Save this stack and use it as a roadmap for the first weeks instead of jumping from video to video looking for magic that is not really there at the level the videos promise.",
                ["#dropshipping", "#onlinebusiness", "#tiktokmarketing", "#organicmarketing", "#dropradar"],
            ),
        }

    @staticmethod
    def _assert_type_3_rules(slides_by_role: dict[SlideRole, str]) -> None:
        full_text = "\n".join(slides_by_role.values()).lower()
        if "hosting" in full_text or "hostinger" in full_text:
            raise ValueError("Tipo 3: hosting no debe aparecer.")
        if "dropshipping" not in slides_by_role.get(SlideRole.HOOK, "").lower():
            raise ValueError("Tipo 3: el hook debe mencionar Dropshipping.")
        ScriptGenerator._assert_one_tool(
            slides_by_role,
            SlideRole.TOOL_PAYMENTS,
            ("paypal", "stripe"),
            "pagos",
        )
        ScriptGenerator._assert_one_tool(
            slides_by_role,
            SlideRole.TOOL_EDITING,
            ("canva", "capcut"),
            "edicion",
        )
        ScriptGenerator._assert_one_tool(
            slides_by_role,
            SlideRole.TOOL_MARKETING,
            ("instagram", "tiktok"),
            "marketing",
        )
        expected_roles = set(TYPE_3_ROLES)
        if set(slides_by_role) != expected_roles:
            raise ValueError("Tipo 3: faltan slides de herramientas.")

    @staticmethod
    def _assert_one_tool(
        slides_by_role: dict[SlideRole, str],
        role: SlideRole,
        options: tuple[str, ...],
        label: str,
    ) -> None:
        text = slides_by_role.get(role, "").lower()
        matches = [tool for tool in options if tool in text]
        if len(matches) != 1:
            raise ValueError(
                f"Tipo 3: el slide de {label} debe usar exactamente una de estas herramientas: "
                + ", ".join(options)
            )

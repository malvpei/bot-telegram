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
            "h1": "Quise hacer dinero con Dropshipping durante 6 meses y esta fue la parte que casi nadie enseña",
            "h2": "Me metí en Dropshipping para ganar dinero y estos números explican por qué casi lo dejé",
            "h3": "Esto fue lo que pasó con mi dinero mes a mes haciendo Dropshipping y el giro no me lo esperaba",
            "h4": "Probé Dropshipping buscando dinero extra y cada foto enseña por qué estuve a punto de rendirme",
            "h5": "Si crees que hacer dinero con Dropshipping es rápido mira cómo fueron mis 6 meses reales",
        }
        october = {
            "o1": "Octubre - 0€\nEmpecé con ganas pero me quedé en parálisis por análisis pensando tanto cada paso que no lancé nada de verdad",
            "o2": "Octubre - 0€\nArranqué motivado aunque perdí demasiado tiempo con el logo y los colores sintiendo que trabajaba mucho sin avanzar",
            "o3": "Octubre - 0€\nTenía todo listo en mi cabeza pero me daba miedo lanzar anuncios y perder dinero así que me bloqueé yo solo",
            "o4": "Octubre - 0€\nMe metí con muchas ganas dudando de cada decisión y acabé con una tienda a medias y cero ventas",
        }
        november = {
            "n1": "Noviembre - 0€\nSeguí en cero intentando vender solo en orgánico mientras veía a otros facturar y yo atascado en el mismo punto",
            "n2": "Noviembre - 0€\nQuise moverlo sin gastar mis ahorros pero el miedo a invertir me frenó y pasó otro mes sin cambios",
            "n3": "Noviembre - 0€\nLo peor fue ver a otros sacar ventas mientras yo seguía a cero y esa comparación me dejó bastante rallado",
            "n4": "Noviembre - 0€\nProbé un par de productos al azar sin que pegara ninguno y entendí que ir a ciegas no iba a funcionar",
        }
        december = {
            "d1": "Diciembre - {amount}€\nLlegó la primera venta gracias al empujón de Navidad y pensé que ya había descubierto el secreto del ecommerce",
            "d2": "Diciembre - {amount}€\nEntró una venta pequeña por la locura navideña y me vine arriba creyendo que a partir de ahí todo sería fácil",
            "d3": "Diciembre - {amount}€\nPor fin cayó la primera venta en Navidad y sentí que lo había pillado aunque me monté una película demasiado pronto",
        }
        january = {
            "j1": "Enero - 0€\nSe acabaron las fiestas y las ventas murieron por completo así que pagar Shopify para nada me dejó sin motivación",
            "j2": "Enero - 0€\nVolví a cero en cuanto pasó Navidad y estuve a punto de dejarlo para buscar un trabajo normal",
            "j3": "Enero - 0€\nEl golpe fue duro porque después de Navidad no entró nada y me frustraba seguir pagando la tienda sin ver resultados",
        }
        february = {
            "f1": "Febrero - {amount}€\nVi a un dropshipper usando Dropradar y me di una última oportunidad eligiendo por datos reales en vez de por intuición",
            "f2": "Febrero - {amount}€\nDescubrí Dropradar por otro chaval que seguía y con una última bala guiada por métricas por fin empezaron a salir ventas",
            "f3": "Febrero - {amount}€\nProbé Dropradar después de ver que otros sacaban productos con datos y al dejar de escoger por gusto personal la tienda arrancó",
        }
        march = {
            "m1": "Marzo - {amount}€\nNo me hice millonario ni me compré un Ferrari pero por fin tenía ingresos estables y dejé de ir totalmente a ciegas",
            "m2": "Marzo - {amount}€\nNada de jets ni mansiones porque la diferencia real fue empezar a usar métricas de verdad y dejar de adivinar",
            "m3": "Marzo - {amount}€\nNo vivo con lujos pero ya tenía ventas sólidas cada mes y aprendí que los datos mandan más que la intuición",
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
            "h1": "I tried to make money with Dropshipping for 6 months and this is the part people skip",
            "h2": "I got into Dropshipping for the money and these numbers show why I nearly quit",
            "h3": "This is what happened to my money month by month with Dropshipping and the turn surprised me",
            "h4": "I tested Dropshipping for extra money and every photo shows why I almost gave up",
            "h5": "If you think making money with Dropshipping is fast watch my real 6 month timeline",
        }
        october = {
            "o1": "October - $0\nI started excited but got stuck in analysis paralysis overthinking every step and never really launching",
            "o2": "October - $0\nI was motivated yet wasted way too much time on the logo and colors feeling busy while nothing actually moved",
            "o3": "October - $0\nEverything looked ready in my head but I was too scared to run ads and lose money so I just kept delaying",
            "o4": "October - $0\nI jumped in with energy but doubted every decision and ended up with a half built store and zero sales",
        }
        november = {
            "n1": "November - $0\nI stayed at zero trying to force organic sales while watching other people making money and feeling stuck",
            "n2": "November - $0\nI wanted to avoid risking my savings so fear kept me frozen and another month passed with the same numbers",
            "n3": "November - $0\nThe worst part was seeing everyone else getting sales while I had nothing and that really got in my head",
            "n4": "November - $0\nI tested a couple of random products without a single one landing and realized winging it was never going to work",
        }
        december = {
            "d1": "December - ${amount}\nMy first sale came in thanks to the Christmas push and I thought I had finally cracked ecommerce",
            "d2": "December - ${amount}\nA small Christmas sale hit and I got carried away believing it would stay that easy from there",
            "d3": "December - ${amount}\nThat first sale during Christmas made me think I had figured it out and I got confident way too quickly",
        }
        january = {
            "j1": "January - $0\nThe holidays ended and sales completely died so paying Shopify for nothing was killing my motivation",
            "j2": "January - $0\nAs soon as Christmas was over I went right back to zero and was close to quitting for a normal job",
            "j3": "January - $0\nReality hit hard because after the holidays nothing came in and I hated paying for a store with no results",
        }
        february = {
            "f1": "February - ${amount}\nI saw another dropshipper using Dropradar and gave myself one last shot picking products from real data not gut",
            "f2": "February - ${amount}\nI found Dropradar through someone I followed and with one last try guided by metrics sales finally started moving",
            "f3": "February - ${amount}\nI tested Dropradar after seeing others rely on data and once I stopped choosing products by taste the store woke up",
        }
        march = {
            "m1": "March - ${amount}\nI did not become a millionaire and did not buy a Ferrari but I finally had stable income and stopped guessing",
            "m2": "March - ${amount}\nNo jets or mansions because the real change was using solid metrics instead of pure intuition",
            "m3": "March - ${amount}\nI am not living some crazy luxury life but the income finally felt stable and I learned data beats guessing",
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
            "h1": "Antes de intentar hacer dinero con Dropshipping mira estas 4 cosas o vas a empezar a ciegas",
            "h2": "Si quieres que Dropshipping te deje dinero estas 4 cosas importan más de lo que parece",
            "h3": "Habría pagado dinero por saber esto antes de empezar Dropshipping porque me habría ahorrado meses",
            "h4": "Estas 4 cosas deciden si Dropshipping te da dinero o si solo te hace perder tiempo",
            "h5": "Si vas en serio con Dropshipping y dinero online necesitas ver la siguiente foto",
        }
        tip1 = {
            "t1": "1. Haz cuentas reales antes de vender\nMucha gente se lanza sin contar comisiones ni devoluciones y no entiende por qué no queda dinero a fin de mes",
            "t2": "1. Los márgenes no se improvisan\nRestar el coste del producto al precio de venta miente casi siempre porque pasarela e impuestos se comen el beneficio",
            "t3": "1. Números claros desde el día uno\nSi no cuentas todos los gastos reales el margen que ves en la hoja de cálculo es pura ficción",
        }
        tip2 = {
            "t1": "2. Una tienda barata nunca vende caro\nTu web decide en segundos si el cliente confía lo suficiente para pagar o se va a buscar en otro sitio",
            "t2": "2. La primera impresión lo es todo\nAunque tu producto sea bueno una web descuidada tira la venta antes de que llegues a contarla",
            "t3": "2. El diseño construye confianza en silencio\nLa gente juzga tu marca en segundos y cada detalle visual le está diciendo si puede fiarse o no",
        }
        tip3 = {
            "t1": "3. Encuentra productos rentables\nBuscar artículos a ciegas quema tiempo y Dropradar te da una forma limpia de ver productos con potencial real",
            "t2": "3. Deja de elegir productos por intuición\nLa suerte no escala y Dropradar filtra oportunidades por datos para que solo pruebes lo que de verdad vende",
            "t3": "3. Atajo a productos que mueven\nDropradar te muestra qué se está vendiendo ahora mismo y por qué funciona sin que tengas que adivinar nada",
        }
        tip4 = {
            "t1": "4. No desaparezcas después de la venta\nUn cliente al que no contestas se convierte rápido en una disputa y en una comisión perdida",
            "t2": "4. El postventa protege tu negocio\nLos problemas casi nunca vienen del envío sino del silencio después de la compra cuando el cliente se siente solo",
            "t3": "4. El soporte es parte de lo que vendes\nResponder rápido y con empatía es la herramienta de retención más barata y más efectiva que vas a tener",
        }
        return self._compose_type_2(Language.ES, hook_options, tip1, tip2, tip3, tip4)

    def _build_type_2_en(self) -> ScriptPackage:
        hook_options = {
            "h1": "Before trying to make money with Dropshipping look at these 4 things or you start blind",
            "h2": "If you want Dropshipping to make money these 4 things matter more than they look",
            "h3": "I would have paid money to know this before starting Dropshipping because it cost me months",
            "h4": "These 4 things decide whether Dropshipping makes money or just burns your time",
            "h5": "If you are serious about Dropshipping and online money you need to see the next photo",
        }
        tip1 = {
            "t1": "1. Know your real numbers\nToo many sellers skip fees and refunds in their math and later wonder why nothing is left at the end of the month",
            "t2": "1. Margins are never obvious\nStaring at the product cost on the supplier page lies almost every time once taxes and platform cuts eat the profit",
            "t3": "1. Run the numbers from day one\nIf you miss the hidden costs the profit you think you see on your spreadsheet is pure fiction",
        }
        tip2 = {
            "t1": "2. A cheap looking store will never sell premium\nYour site decides in seconds whether a visitor trusts you enough to buy or leaves to check somewhere else",
            "t2": "2. First impressions decide the sale\nEven a solid product dies on a messy storefront and you lose the order before you can even count it",
            "t3": "2. Design builds trust quietly\nPeople size up your brand in seconds and every visual detail is telling the buyer whether to trust you or not",
        }
        tip3 = {
            "t1": "3. Find profitable products\nRandom hunting burns time fast and Dropradar gives you a cleaner way to spot items with real potential behind them",
            "t2": "3. Stop picking products on gut feeling\nLuck does not scale and Dropradar filters opportunities by real data so you only test the things that can actually sell",
            "t3": "3. Shortcut to items that move\nDropradar shows you what is selling right now and why it works so you never have to guess a winner again",
        }
        tip4 = {
            "t1": "4. Do not vanish after the sale\nAn ignored customer turns into a chargeback much faster than you think and that hit costs more than the sale itself",
            "t2": "4. After sales care protects the business\nMost disputes do not come from shipping but from silence once the customer has paid and feels alone",
            "t3": "4. Support is part of what you sell\nReplying quickly and with empathy is the cheapest and most effective retention tool you will ever have",
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
            "h1": "Como empezar en Dropshipping en 2026",
            "h2": "Como hacer Dropshipping en 2026",
            "h3": "Empieza a hacer Dropshipping en 2026\nnunca habia sido tan facil",
            "h4": "Como montar tu primera tienda de Dropshipping en 2026",
            "h5": "Guia rapida para empezar Dropshipping en 2026",
        }
        tools = {
            SlideRole.TOOL_STORE: "1. Tienda\nConstruye tu tienda por solo 1€\nUsa Shopify",
            SlideRole.TOOL_PRODUCT_SEARCH: "2. Busqueda de productos\nEncuentra productos ganadores\nUsa Dropradar",
            SlideRole.TOOL_SCRIPTS: "3. Guiones\nSigue guiones para tus videos\nUsa ChatGPT",
            SlideRole.TOOL_PAYMENTS: random.choice(
                (
                    "4. Pagos\nGestiona tus pagos y cobros con confianza\nUsa PayPal",
                    "4. Pagos\nGestiona tus pagos de forma segura\nUsa Stripe",
                )
            ),
            SlideRole.TOOL_EDITING: random.choice(
                (
                    "5. Edicion\nCrea diseños y piezas visuales para tu marca\nUsa Canva",
                    "5. Edicion\nEdita tus videos para mas calidad\nUsa CapCut",
                )
            ),
            SlideRole.TOOL_MARKETING: random.choice(
                (
                    "6. Marketing\nPublica contenido visual y crea comunidad\nUsa Instagram",
                    "6. Marketing\nPromociona organicamente con videos cortos\nUsa TikTok",
                )
            ),
        }
        return self._compose_type_3(Language.ES, hooks, tools)

    def _build_type_3_en(self) -> ScriptPackage:
        hooks = {
            "h1": "How to start Dropshipping in 2026",
            "h2": "How to do Dropshipping in 2026",
            "h3": "Start Dropshipping in 2026\nit has never been this easy",
            "h4": "How to build your first Dropshipping store in 2026",
            "h5": "Quick guide to start Dropshipping in 2026",
        }
        tools = {
            SlideRole.TOOL_STORE: "1. Store\nBuild your store for only $1\nUse Shopify",
            SlideRole.TOOL_PRODUCT_SEARCH: "2. Product Search\nFind winning products\nUse Dropradar",
            SlideRole.TOOL_SCRIPTS: "3. Scripts\nFollow scripts for your videos\nUse ChatGPT",
            SlideRole.TOOL_PAYMENTS: random.choice(
                (
                    "4. Payments\nManage customer payments with confidence\nUse PayPal",
                    "4. Payments\nManage your payments securely\nUse Stripe",
                )
            ),
            SlideRole.TOOL_EDITING: random.choice(
                (
                    "5. Editing\nCreate clean visuals and brand assets\nUse Canva",
                    "5. Editing\nEdit your videos for better quality\nUse CapCut",
                )
            ),
            SlideRole.TOOL_MARKETING: random.choice(
                (
                    "6. Marketing\nPost visual content and build community\nUse Instagram",
                    "6. Marketing\nPromote organically with short videos\nUse TikTok",
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
        description = self._develop_social_copy_description(
            video_type,
            language,
            key,
            description,
        )
        return key, SocialCopy(
            title=title,
            description=description,
            hashtags=hashtags,
        )

    def _develop_social_copy_description(
        self,
        video_type: VideoType,
        language: Language,
        key: str,
        description: str,
    ) -> str:
        additions = self._social_copy_description_additions(video_type, language)
        extra = additions.get(key)
        if not extra:
            return description
        return f"{description} {extra}"

    def _social_copy_description_additions(
        self,
        video_type: VideoType,
        language: Language,
    ) -> dict[str, str]:
        if language == Language.EN:
            if video_type == VideoType.TYPE_1:
                return {
                    "en1": "I wanted the carousel to feel like a real timeline, not a flex, because the months with no sales are exactly where most beginners panic and quit before the useful lesson appears.",
                    "en2": "The important part is seeing the order of the decisions, because one small change in how I judged products made the later numbers make much more sense.",
                    "en3": "Each slide is there to make the next one matter, from the first doubts to the moment where the process finally stopped feeling random.",
                    "en4": "Use it as a reality check before chasing the next shiny product, because the money only started making sense when the testing process got more disciplined.",
                }
            if video_type == VideoType.TYPE_2:
                return {
                    "en1": "The goal is not to scare you, it is to make the first steps feel clearer so you know what to fix before spending money on traffic.",
                    "en2": "Read each point as a quick audit of your own store, because one weak area can make the rest of the setup look worse than it really is.",
                    "en3": "This is the kind of checklist I wish I had beside me before paying for ads, choosing products or assuming the problem was just the creative.",
                    "en4": "If one slide feels uncomfortable, that is probably the part worth checking first before you put more money or time into the store.",
                }
        if video_type == VideoType.TYPE_1:
            return {
                "es1": "La idea es que cada foto te obligue a ver la siguiente, porque el mes malo no se entiende igual cuando sabes lo que vino despues y por que cambie la forma de elegir productos.",
                "es2": "Lo importante no es solo la cifra final, sino ver el orden de decisiones que me hizo pasar de probar por probar a entender que señales estaba mirando.",
                "es3": "Cada slide esta pensada como una parte de la historia: la duda, el bloqueo, el intento fallido y el momento en el que el metodo empezo a tener sentido.",
                "es4": "Usalo como una referencia realista antes de perseguir otro producto viral, porque el dinero empezo a ordenarse cuando deje de improvisar cada prueba.",
            }
        if video_type == VideoType.TYPE_2:
            return {
                "es1": "No va de asustarte, va de que empieces con mas claridad y sepas que revisar antes de meter dinero en trafico o dar por perdido un producto.",
                "es2": "Lee cada punto como una mini auditoria de tu tienda, porque a veces una sola parte floja hace que todo el sistema parezca peor de lo que es.",
                "es3": "Es la checklist que me habria gustado tener delante antes de pagar anuncios, elegir productos o pensar que el problema era solo el creativo.",
                "es4": "Si una de las fotos te incomoda, probablemente esa sea la parte que necesitas arreglar antes de meter mas dinero o mas horas en la tienda.",
            }
        return {}

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
                    "No fue una linea recta: empece con cero ventas, me atasque probando cosas al azar y hubo un punto en el que casi lo deje. Lo que cambio no fue encontrar un producto magico, fue empezar a mirar datos reales, comparar señales y dejar de tomar decisiones solo por intuicion. Si estas empezando, este video resume la parte que normalmente nadie ensena.",
                    ["#dropshipping", "#ecommerce", "#emprender", "#tiendaonline", "#dropradar"],
                ),
                "es2": (
                    "De cero ventas a un sistema con datos",
                    "La parte que casi nadie cuenta es que los primeros meses pueden ser bastante frustrantes: tienda abierta, horas metidas y resultados que no llegan. En mi caso el salto vino cuando deje de escoger productos a ciegas y empece a validar oportunidades con informacion mas clara. No es una historia de lujo rapido, es una historia de aprender a medir antes de escalar.",
                    ["#dropshippingespana", "#ecommerce", "#ventasonline", "#emprendedores", "#dropradar"],
                ),
                "es3": (
                    "Lo que aprendi despues de casi rendirme",
                    "Si estas empezando y sientes que todo va demasiado lento, mira esto antes de pensar que el problema eres tu. Muchas veces el bloqueo no esta en trabajar poco, sino en probar productos sin criterio, copiar tiendas sin entenderlas y no saber que mirar. Cuando tienes un sistema para elegir mejor, cada prueba te ensena algo en vez de quemarte.",
                    ["#dropshipping", "#negociosonline", "#ecommercetips", "#shopify", "#dropradar"],
                ),
                "es4": (
                    "Mis numeros cambiaron cuando cambie el metodo",
                    "El salto no vino de un producto magico ni de una tienda perfecta a la primera. Vino de aceptar que mi gusto personal no era suficiente, comparar datos de productos, mirar demanda, creativos y señales de venta, y tomar decisiones con menos ego. Para mi, esa fue la diferencia entre adivinar y construir un proceso repetible.",
                    ["#emprendimiento", "#dropshipping", "#productoganador", "#ecommerce", "#dropradar"],
                ),
            }
        if video_type == VideoType.TYPE_2:
            return {
                "es1": (
                    "4 cosas que me habria gustado saber antes",
                    "Guardar esto te puede ahorrar meses de prueba y error si estas montando tu primera tienda. Antes de pensar solo en anuncios o productos virales, necesitas entender margenes, confianza, busqueda de producto y soporte al cliente. Son bases simples, pero si fallan, todo lo demas se vuelve mucho mas dificil de escalar.",
                    ["#dropshipping", "#ecommerce", "#shopify", "#emprenderonline", "#dropradar"],
                ),
                "es2": (
                    "La checklist basica antes de vender online",
                    "Margenes, confianza, producto y soporte: cuatro areas que parecen basicas, pero deciden si una tienda aguanta o se rompe. Puedes tener buen trafico, pero si no entiendes tus costes reales, tu web no genera confianza o eliges productos sin datos, las ventas no compensan el esfuerzo. Usa esta checklist antes de lanzar o antes de meter mas presupuesto.",
                    ["#ecommercetips", "#dropshippingtips", "#tiendaonline", "#ventas", "#dropradar"],
                ),
                "es3": (
                    "Antes de lanzar anuncios, revisa esto",
                    "Muchos fallos no vienen solo del producto, vienen de vender sin numeros claros y sin un sistema para decidir que probar. Antes de gastar en anuncios, revisa si el margen aguanta comisiones, devoluciones y costes de adquisicion, y si tu tienda transmite confianza en segundos. Un buen producto ayuda, pero una mala estructura puede matar la venta antes de empezar.",
                    ["#dropshipping", "#marketingdigital", "#shopifytips", "#negociosonline", "#dropradar"],
                ),
                "es4": (
                    "4 lecciones para no empezar a ciegas",
                    "Si estas probando productos al azar, cambia el enfoque antes de quemar presupuesto. El dropshipping se vuelve mucho mas claro cuando sabes que revisar: numeros, percepcion de marca, demanda real y experiencia del cliente despues de comprar. Este video no es teoria bonita, es una guia rapida para evitar errores que se pagan caros.",
                    ["#ecommerce", "#dropshippingespana", "#emprendedores", "#ventasonline", "#dropradar"],
                ),
            }
        return {
            "es1": (
                "Como empezar dropshipping en 2026",
                "Estas son las herramientas base para empezar sin complicarte mas de la cuenta: montar la tienda, buscar productos con datos, crear guiones, gestionar pagos, editar contenido y mover trafico organico. La clave no es tener mil apps, sino usar pocas herramientas que cubran las partes importantes del proceso. Empieza simple, valida rapido y mejora cuando ya tengas senales reales.",
                ["#dropshipping2026", "#ecommerce", "#shopify", "#tiktokmarketing", "#dropradar"],
            ),
            "es2": (
                "Tu stack para lanzar una tienda online",
                "No necesitas mil herramientas para lanzar tu primera tienda online. Necesitas una base para vender, una forma de encontrar productos con potencial, un sistema para crear contenido y una manera sencilla de cobrar, editar y promocionar. Este stack esta pensado para empezar ligero, no para perder semanas configurando cosas antes de validar.",
                ["#dropshipping", "#tiendaonline", "#herramientas", "#emprender", "#dropradar"],
            ),
            "es3": (
                "Herramientas para empezar desde cero",
                "De tienda a producto, guiones, pagos, edicion y trafico organico: este es el orden simple para no perderte al empezar. Primero crea una estructura minima, luego busca productos con criterio, prepara contenido que puedas publicar y mide la respuesta del mercado. Lo importante al principio es avanzar con claridad y no quedarte bloqueado por exceso de opciones.",
                ["#ecommerce2026", "#dropshippingtips", "#shopify", "#capcut", "#dropradar"],
            ),
            "es4": (
                "La ruta simple para tu primera tienda",
                "Si lo estas aplazando porque no sabes que herramientas usar, empieza por esta combinacion y prueba rapido. Una tienda sencilla, productos elegidos con datos, guiones claros, pagos bien montados, edicion agil y trafico organico pueden darte suficiente feedback para saber si vas por buen camino. Despues optimizas, pero primero necesitas poner algo real delante del mercado.",
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
                    "It was not a straight line: zero sales, doubts, random testing and one moment where quitting felt easier than trying again. What changed was not a magic product, it was learning to read real signals, compare opportunities and stop choosing based only on gut feeling. If you are starting out, this is the honest part most people skip.",
                    ["#dropshipping", "#ecommerce", "#onlinebusiness", "#shopify", "#dropradar"],
                ),
                "en2": (
                    "What changed after months of guessing",
                    "The shift was not luck and it did not happen overnight. I spent months guessing, overthinking the store and testing products without a clear reason, then realized the process needed better data. Once I started looking at demand, product signals and content angles more seriously, every test became easier to understand.",
                    ["#dropshippingtips", "#ecommercebusiness", "#entrepreneur", "#productresearch", "#dropradar"],
                ),
                "en3": (
                    "From almost quitting to clearer numbers",
                    "If you are starting out, watch this before blaming yourself for slow results. Sometimes the problem is not effort, it is testing products blindly, copying stores without context and having no clear way to judge what is worth trying. A better decision system will not make everything easy, but it makes every test more useful.",
                    ["#dropshipping", "#ecommercejourney", "#shopifystore", "#onlineincome", "#dropradar"],
                ),
                "en4": (
                    "The lesson my first sales taught me",
                    "The product was only part of it. The real unlock was accepting that personal taste is not a strategy, then choosing with less ego and more data around demand, creatives, competition and sales signals. That shift made dropshipping feel less like gambling and more like a process I could actually improve.",
                    ["#ecommerce", "#dropshippingbusiness", "#digitalbusiness", "#shopifytips", "#dropradar"],
                ),
            }
        if video_type == VideoType.TYPE_2:
            return {
                "en1": (
                    "4 things I wish I knew before dropshipping",
                    "Save this before launching your first store. Before thinking only about ads or viral products, you need to understand margins, trust, product research and customer support. These basics are not flashy, but if one of them breaks, the whole store becomes harder to scale.",
                    ["#dropshipping", "#ecommerce", "#shopify", "#dropshippingtips", "#dropradar"],
                ),
                "en2": (
                    "The simple checklist before selling online",
                    "Margins, trust, product research and support: four areas that decide whether an online store survives or quietly bleeds money. You can have traffic, but if your numbers are unclear, your site feels unsafe or your product logic is weak, the sales will not fix the structure. Use this as a quick checklist before spending more budget.",
                    ["#ecommercetips", "#onlinebusiness", "#shopifystore", "#productresearch", "#dropradar"],
                ),
                "en3": (
                    "Watch this before running ads",
                    "A lot of stores fail before traffic even has a real chance because the numbers and product logic are not clear. Before running ads, check whether your margin can survive fees, refunds and acquisition costs, and whether the store builds trust fast enough. A good product helps, but a weak setup can kill the sale first.",
                    ["#dropshippingtips", "#ecommercemarketing", "#shopifytips", "#digitalmarketing", "#dropradar"],
                ),
                "en4": (
                    "4 lessons so you do not start blind",
                    "Random product testing burns budget quickly. Dropshipping becomes much clearer when you know what to check first: numbers, perceived trust, real demand and the customer experience after purchase. This is a short practical guide for avoiding the beginner mistakes that cost the most.",
                    ["#dropshipping", "#ecommercebusiness", "#entrepreneurtips", "#onlinestore", "#dropradar"],
                ),
            }
        return {
            "en1": (
                "How to start dropshipping in 2026",
                "These are the core tools for starting without overcomplicating the process: building the store, researching products with data, creating scripts, taking payments, editing content and driving organic traffic. You do not need a huge software stack at the beginning. You need a simple setup that lets you validate fast and improve once the market gives you real feedback.",
                ["#dropshipping2026", "#ecommerce", "#shopify", "#tiktokmarketing", "#dropradar"],
            ),
            "en2": (
                "Your starter stack for an online store",
                "You do not need a hundred tools to launch your first online store. You need a selling platform, a cleaner way to find products, a content workflow, payment setup, fast editing and a traffic source you can practice every day. This stack is built for momentum, not for spending weeks configuring things before you test.",
                ["#dropshipping", "#onlinestore", "#ecommercetools", "#entrepreneur", "#dropradar"],
            ),
            "en3": (
                "Tools to start from zero",
                "Store, product research, scripts, payments, editing and organic traffic: this is the simple order if you are starting from zero. Build the minimum structure first, then choose products with clearer signals, publish content consistently and measure what the market responds to. The goal is not perfection, it is useful feedback.",
                ["#ecommerce2026", "#dropshippingtips", "#shopify", "#capcut", "#dropradar"],
            ),
            "en4": (
                "The simple route to your first store",
                "If you keep delaying because you do not know what to use, start with this setup and test fast. A simple store, data-backed product research, clear scripts, payments, quick editing and organic content can give you enough feedback to know if you are moving in the right direction. Optimize later, but get something real in front of the market first.",
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

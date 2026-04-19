from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from app.models import (
    Language,
    ScriptPackage,
    SlideRole,
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
            "h1": "Lo que gané de verdad con Dropshipping en mis últimos 6 meses y por qué estuve a nada de dejarlo",
            "h2": "Mis números reales haciendo Dropshipping estos 6 meses y la razón por la que casi tiré la toalla",
            "h3": "Exactamente lo que saqué con Dropshipping en 6 meses y por qué hubo un momento en que quería dejarlo",
            "h4": "Las ganancias reales de mis últimos 6 meses de Dropshipping y por qué casi mandé todo a la basura",
            "h5": "Estos son mis números reales haciendo Dropshipping en 6 meses y lo cerca que estuve de rendirme",
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
            "h1": "Exactly what I made with Dropshipping in my last 6 months and why I nearly gave up",
            "h2": "My real Dropshipping numbers from the last 6 months and the reason I almost quit",
            "h3": "What I actually made with Dropshipping in 6 months and why I came close to throwing it away",
            "h4": "The real money I made from Dropshipping in my last 6 months and why I almost walked away",
            "h5": "These are my honest 6 month Dropshipping numbers and how close I was to quitting",
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
        )

    # ------------------------------------------------------------------
    # Type 2 — "4 things I wish I knew" tips
    # ------------------------------------------------------------------

    def _build_type_2_es(self) -> ScriptPackage:
        hook_options = {
            "h1": "Las 4 cosas que me habría encantado saber cuando empecé en Dropshipping",
            "h2": "Las únicas 4 cosas que de verdad deberías saber para sacar ingresos con Dropshipping",
            "h3": "Literalmente habría pagado por saber estas 4 cosas al empezar en Dropshipping",
            "h4": "Las 4 cosas que me habrían ahorrado meses de prueba y error en Dropshipping",
            "h5": "Las 4 cosas que ojalá alguien me hubiera contado antes de meterme en Dropshipping",
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
        return self._compose_type_2(hook_options, tip1, tip2, tip3, tip4)

    def _build_type_2_en(self) -> ScriptPackage:
        hook_options = {
            "h1": "The 4 things I wish I knew when I started with Dropshipping",
            "h2": "The only 4 things you really need to know to make money with Dropshipping",
            "h3": "I genuinely would have paid to know these 4 things when I started Dropshipping",
            "h4": "These 4 things would have saved me months of trial and error in Dropshipping",
            "h5": "The 4 things I wish someone had told me before I jumped into Dropshipping",
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
        return self._compose_type_2(hook_options, tip1, tip2, tip3, tip4)

    def _compose_type_2(
        self,
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

        signature = _hash_signature(
            [
                hook_key,
                keys[SlideRole.TIP1],
                keys[SlideRole.TIP2],
                keys[SlideRole.TIP3],
                keys[SlideRole.TIP4],
            ]
        )

        ordered = [slides_by_role[role] for role in TYPE_2_ROLES]
        self._assert_type_2_rules(slides_by_role)
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=signature,
            plain_text="\n\n".join(ordered),
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
            SlideRole.TOOL_PAYMENTS: "4. Pagos\nGestiona tus pagos de forma segura\nUsa PayPal o Stripe",
            SlideRole.TOOL_EDITING: "5. Edicion\nEdita tus videos para mas calidad\nUsa CapCut",
            SlideRole.TOOL_MARKETING: "6. Marketing\nPromociona organicamente\nUsa TikTok",
        }
        return self._compose_type_3(hooks, tools)

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
            SlideRole.TOOL_PAYMENTS: "4. Payments\nManage your payments securely\nUse PayPal or Stripe",
            SlideRole.TOOL_EDITING: "5. Editing\nEdit your videos for better quality\nUse CapCut",
            SlideRole.TOOL_MARKETING: "6. Marketing\nPromote your product organically\nUse TikTok",
        }
        return self._compose_type_3(hooks, tools)

    def _compose_type_3(
        self,
        hook_options: dict[str, str],
        tools: dict[SlideRole, str],
    ) -> ScriptPackage:
        hook_key = random.choice(list(hook_options))
        slides_by_role = {SlideRole.HOOK: hook_options[hook_key], **tools}
        ordered = [slides_by_role[role] for role in TYPE_3_ROLES]
        signature = _hash_signature([hook_key, *ordered[1:]])
        self._assert_type_3_rules(slides_by_role)
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=signature,
            plain_text="\n\n".join(ordered),
        )

    @staticmethod
    def _assert_type_3_rules(slides_by_role: dict[SlideRole, str]) -> None:
        full_text = "\n".join(slides_by_role.values()).lower()
        if "hosting" in full_text or "hostinger" in full_text:
            raise ValueError("Tipo 3: hosting no debe aparecer.")
        if "dropshipping" not in slides_by_role.get(SlideRole.HOOK, "").lower():
            raise ValueError("Tipo 3: el hook debe mencionar Dropshipping.")
        expected_roles = set(TYPE_3_ROLES)
        if set(slides_by_role) != expected_roles:
            raise ValueError("Tipo 3: faltan slides de herramientas.")

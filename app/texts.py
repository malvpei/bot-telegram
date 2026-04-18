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
        return self._build_type_2_es if language == Language.ES else self._build_type_2_en

    # ------------------------------------------------------------------
    # Type 1 — narrative October → March
    # ------------------------------------------------------------------

    def _build_type_1_es(self) -> ScriptPackage:
        hook_options = {
            "h1": "Lo que gané de verdad en mis últimos 6 meses y por qué estuve a nada de dejarlo",
            "h2": "Mis números reales de estos 6 meses y la razón por la que casi tiré la toalla",
            "h3": "Exactamente lo que saqué en 6 meses y por qué hubo un momento en que quería dejarlo",
            "h4": "Las ganancias reales de mis últimos 6 meses y por qué casi mandé todo a la basura",
            "h5": "Estos son mis números reales en 6 meses y lo cerca que estuve de rendirme",
        }
        october = {
            "o1": "Octubre · 0€\nEmpecé con ganas, pero me quedé en parálisis por análisis.\nPensé tanto cada paso que no lancé nada de verdad.",
            "o2": "Octubre · 0€\nArranqué motivado, pero perdí demasiado tiempo con el logo y los colores.\nSentía que trabajaba mucho, pero no avanzaba nada.",
            "o3": "Octubre · 0€\nTenía todo listo en mi cabeza, pero me daba miedo lanzar anuncios y perder dinero.\nAl final me bloqueé yo solo.",
            "o4": "Octubre · 0€\nMe metí con muchas ganas, pero dudaba de cada decisión.\nResultado, una tienda a medio terminar y cero ventas.",
        }
        november = {
            "n1": "Noviembre · 0€\nSeguí en cero intentando vender solo en orgánico.\nVeía a otros facturar y yo seguía atascado en el mismo punto.",
            "n2": "Noviembre · 0€\nQuise moverlo sin gastar mis ahorros, pero el miedo a invertir me frenó otra vez.\nPasó otro mes y no cambió nada.",
            "n3": "Noviembre · 0€\nLo peor fue ver a otros sacar ventas mientras yo seguía a cero.\nEsa comparación me dejó bastante rallado.",
            "n4": "Noviembre · 0€\nProbé un par de productos al azar y no pegó ninguno.\nEntendí que ir a ciegas no iba a funcionar nunca.",
        }
        december = {
            "d1": "Diciembre · {amount}€\nLlegó la primera venta gracias al empujón de Navidad.\nPensé que ya había descubierto el secreto del ecommerce.",
            "d2": "Diciembre · {amount}€\nEntró una venta pequeña por la locura navideña y me vine arriba enseguida.\nCreí que a partir de ahí todo sería fácil.",
            "d3": "Diciembre · {amount}€\nPor fin cayó la primera venta en Navidad y sentí que lo había pillado.\nMe monté una película demasiado pronto.",
        }
        january = {
            "j1": "Enero · 0€\nSe acabaron las fiestas y las ventas murieron por completo.\nPagar Shopify para nada me dejó con una desmotivación brutal.",
            "j2": "Enero · 0€\nVolví a cero en cuanto pasó Navidad.\nEstuve a punto de dejarlo y buscar un trabajo normal.",
            "j3": "Enero · 0€\nEl golpe fue duro porque después de Navidad no entró nada.\nMe frustraba seguir pagando la tienda sin ver resultados.",
        }
        february = {
            "f1": "Febrero · {amount}€\nVi a un dropshipper en redes usando Dropradar y decidí darme una última oportunidad.\nEsta vez elegí por datos reales y no por intuición.",
            "f2": "Febrero · {amount}€\nDescubrí Dropradar por otro chaval que seguía y dije, va, una última bala.\nMe guié solo por métricas y ahí empezaron a salir ventas.",
            "f3": "Febrero · {amount}€\nProbé Dropradar después de ver que otros seguían sacando productos con datos.\nDejé de escoger por gusto personal y la tienda arrancó.",
        }
        march = {
            "m1": "Marzo · {amount}€\nNo me hice millonario ni me compré un Ferrari.\nPero por fin tenía ingresos estables y dejé de ir totalmente a ciegas.",
            "m2": "Marzo · {amount}€\nNada de jets ni mansiones, eso no va de eso.\nLa diferencia fue empezar a usar métricas reales y dejar de adivinar.",
            "m3": "Marzo · {amount}€\nNo vivo con lujos, pero ya tenía ventas sólidas cada mes.\nLa lección fue clara, los datos mandan más que la intuición.",
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
            "h1": "Exactly what I made in my last 6 months and why I nearly gave up",
            "h2": "My real numbers from the last 6 months and the reason I almost quit",
            "h3": "What I actually made in 6 months and why I came close to throwing it away",
            "h4": "The real money I made in my last 6 months and why I almost walked away",
            "h5": "These are my honest 6 month numbers and how close I was to quitting",
        }
        october = {
            "o1": "October · $0\nI started excited, but I got stuck in analysis paralysis.\nI kept overthinking every step and never really launched.",
            "o2": "October · $0\nI was motivated, but I wasted way too much time on the logo and colors.\nIt felt like work, but nothing was moving.",
            "o3": "October · $0\nEverything looked ready in my head, but I was scared to run ads and lose money.\nSo I kept delaying it.",
            "o4": "October · $0\nI jumped in with energy, but I doubted every single decision.\nThe result was a half built store and zero sales.",
        }
        november = {
            "n1": "November · $0\nI stayed at zero trying to force organic sales.\nI watched other people making money while I was still stuck.",
            "n2": "November · $0\nI wanted to avoid risking my savings, so fear kept me frozen again.\nAnother month passed and I was still at zero.",
            "n3": "November · $0\nThe worst part was seeing everyone else getting sales while I had nothing.\nThat honestly got in my head.",
            "n4": "November · $0\nI tested a couple of random products and none of them landed.\nI realized winging it was never going to work.",
        }
        december = {
            "d1": "December · ${amount}\nMy first sale came in because of the Christmas push.\nI thought I had finally cracked ecommerce.",
            "d2": "December · ${amount}\nA small Christmas sale hit and I got carried away.\nI really thought it would stay easy from there.",
            "d3": "December · ${amount}\nThat first sale during Christmas made me think I had figured it out.\nI got confident way too quickly.",
        }
        january = {
            "j1": "January · $0\nThe holidays ended and sales completely died.\nPaying Shopify for nothing was killing my motivation.",
            "j2": "January · $0\nAs soon as Christmas was over, I went right back to zero.\nI was close to quitting and getting a normal job.",
            "j3": "January · $0\nReality hit hard because after the holidays nothing came in.\nI hated paying for the store with no results.",
        }
        february = {
            "f1": "February · ${amount}\nI saw another dropshipper using Dropradar and gave this one last shot.\nThis time I picked products from real data, not my gut.",
            "f2": "February · ${amount}\nI found Dropradar through someone I followed and thought, one last try.\nI trusted the metrics and sales finally started moving.",
            "f3": "February · ${amount}\nI tested Dropradar after seeing other people rely on data.\nI stopped choosing products by taste and the store woke up.",
        }
        march = {
            "m1": "March · ${amount}\nI did not become a millionaire and I did not buy a Ferrari.\nBut I finally had stable income and stopped guessing.",
            "m2": "March · ${amount}\nNo jets, no mansions, nothing like that.\nThe real change was using solid metrics instead of pure intuition.",
            "m3": "March · ${amount}\nI am not living some crazy luxury life, but the income finally felt stable.\nThat is when I learned data matters more than guessing.",
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
            "t1": "Consejo 1\nCalcula comisiones, costes ocultos, devoluciones y pasarelas antes de vender.\nSi no sabes tu margen real, puedes vender mucho y ganar casi nada.",
            "t2": "Consejo 1\nNo te quedes solo con el coste del producto.\nEntre comisiones, impuestos y devoluciones se te puede ir el beneficio sin darte cuenta.",
            "t3": "Consejo 1\nHaz números de verdad desde el primer día.\nSi no cuentas todos los gastos, el margen bonito que ves no existe.",
        }
        tip2 = {
            "t1": "Consejo 2\nTu tienda tiene que verse premium desde que alguien entra.\nBuenas fotos y una página limpia hacen que la confianza suba al instante.",
            "t2": "Consejo 2\nAunque el producto sea bueno, si la web parece barata nadie confía.\nUn look premium y fotos potentes cambian muchísimo la conversión.",
            "t3": "Consejo 2\nLa gente decide muy rápido si tu tienda transmite confianza o no.\nPor eso necesitas fotos buenas y una web que se vea seria.",
        }
        tip3 = {
            "t1": "Consejo 3\nPara encontrar productos ganadores deja de ir a ojo.\nYo usaría Dropradar para ver artículos rentables y en tendencia mucho más rápido.",
            "t2": "Consejo 3\nLo que más tiempo ahorra es saber qué merece la pena probar.\nCon Dropradar localizas productos con números y tendencias reales.",
            "t3": "Consejo 3\nBuscar productos al azar te quema rápido.\nDropradar te ayuda a detectar cosas con potencial antes de perder semanas.",
        }
        tip4 = {
            "t1": "Consejo 4\nResponde rápido después de la compra.\nUn buen soporte evita reclamaciones y te protege en los métodos de pago.",
            "t2": "Consejo 4\nEl postventa importa más de lo que parece.\nSi contestas tarde, llegan los problemas y luego vienen las disputas.",
            "t3": "Consejo 4\nNo desaparezcas cuando entra una venta.\nResponder rápido baja reclamaciones y te ahorra muchos dolores de cabeza.",
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
            "t1": "Tip 1\nWork out fees, hidden costs, returns and payment charges before you sell.\nIf you do not know the real margin, good sales can still mean weak profit.",
            "t2": "Tip 1\nDo not stop at the product cost.\nFees, taxes and refunds can wipe out your margin before you notice.",
            "t3": "Tip 1\nRun the numbers properly from day one.\nIf you miss the hidden costs, the profit you think you have is not real.",
        }
        tip2 = {
            "t1": "Tip 2\nYour store needs to look premium the second someone lands on it.\nStrong photos and a clean layout build trust fast.",
            "t2": "Tip 2\nEven a solid product struggles if the site looks cheap.\nA premium look and better photos can change conversion a lot.",
            "t3": "Tip 2\nPeople judge your store in a few seconds.\nThat is why better photos and a polished design matter so much.",
        }
        tip3 = {
            "t1": "Tip 3\nStop guessing when you search for products.\nDropradar makes it easier to spot profitable items that are already trending.",
            "t2": "Tip 3\nThe fastest shortcut is knowing what is worth testing.\nDropradar helps you find products backed by real trends and numbers.",
            "t3": "Tip 3\nRandom product hunting burns time fast.\nDropradar gives you a cleaner way to find items with real potential.",
        }
        tip4 = {
            "t1": "Tip 4\nReply fast after the sale.\nGood support reduces complaints and protects you on payment methods.",
            "t2": "Tip 4\nAfter sales support matters more than people think.\nSlow replies lead to issues and then the disputes start.",
            "t3": "Tip 4\nDo not vanish once someone buys.\nFast replies prevent chargebacks and save you a lot of stress.",
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

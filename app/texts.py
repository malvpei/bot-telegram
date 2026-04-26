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
SOCIAL_DESCRIPTION_TARGET_MIN = 2400
SOCIAL_DESCRIPTION_TARGET_MAX = 3200


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
        variants = {
            "a": {
                SlideRole.HOOK: "Exactamente cuánto gané haciendo Dropshipping en estos 6 meses y por qué casi lo dejé...",
                SlideRole.OCTOBER: "Octubre - 0€\nLancé mi primera tienda supermotivado. Puse algo de dinero en anuncios, tuve un montón de vistas, pero nadie compró. Fue un buen golpe de realidad y perdí mi presupuesto.",
                SlideRole.NOVEMBER: "Noviembre - 0€\nPausé los anuncios de golpe para no perder más dinero. Me pasé todo el mes tocando el diseño de la tienda e intentando conseguir más visitas orgánicas. Igualmente, seguía en 0 ventas.",
                SlideRole.DECEMBER: "Diciembre - 0€\nLa campaña navideña pasó de largo. Veía a todo el mundo facturando y yo seguía atascado, sobrepensando qué producto lanzar por miedo a equivocarme otra vez.",
                SlideRole.JANUARY: "Enero - 0€\nNi siquiera abría Shopify. Estaba frustrado de pagar la cuota mensual para nada, estuve a un solo clic de cancelar mi suscripción. Sentía que todo esto era una pérdida de tiempo.",
                SlideRole.FEBRUARY: "Febrero - 800€\nVi a un dropshipper que sigo recomendando Dropradar y decidí hacer el último intento. Elegí un producto basándome estrictamente en sus métricas y, para mi sorpresa, empezaron a entrar ventas rentables.",
                SlideRole.MARCH: "Marzo - 2700€\nPor fin tengo ventas de forma constante. Estuve a punto de rendirme antes de aprender que lo que importa es la constancia y saber actuar sobre métricas y datos reales.",
            },
            "b": {
                SlideRole.HOOK: "Exactamente cuánto facturé en mis primeros 6 meses en Dropshipping y por qué casi lo dejé...",
                SlideRole.OCTOBER: "Octubre - 0€\nEmpecé con muchas ganas, pero sin tener ni idea. Me pasé el mes montando la web y buscando productos que me parecieran buenos, pero no conseguí ni una sola venta.",
                SlideRole.NOVEMBER: "Noviembre - 0€\nMe frustraba ver que pasaban las semanas y no avanzaba. Seguía retocando la tienda y mirando tutoriales, pero me daba miedo empezar con anuncios y perder dinero, así que me quedé estancado.",
                SlideRole.DECEMBER: "Diciembre - 0€\nVeía a todo el mundo facturando por Navidad y yo seguía igual. Me sentía incapaz de encontrar un producto que funcionara y la presión de ver que otros lo conseguían me estaba quemando.",
                SlideRole.JANUARY: "Enero - 0€\nEstaba totalmente desmotivado. Pagar la cuota de Shopify sin vender nada me parecía tirar el dinero y estuve a un paso de cerrar la cuenta y olvidarme de todo.",
                SlideRole.FEBRUARY: "Febrero - 680€\nVi a un dropshipper que sigo usando Dropradar y decidí darle una última oportunidad. Elegí un producto basándome en sus datos y métricas y, por primera vez, empecé a vender de verdad.",
                SlideRole.MARCH: "Marzo - 3100€\nNo soy millonario, pero por fin tengo un negocio que funciona. Me alegro de no haberme rendido en enero; la clave era la constancia y dejar de adivinar qué producto iba a funcionar.",
            },
        }
        return self._compose_type_1_fixed(language=Language.ES, variants=variants)
        hook_options = {
            "h1": "Exactamente cuánto dinero gané con Dropshipping en 6 meses empezando desde cero",
            "h2": "Exactamente cuánto facturé con Dropshipping en 6 meses desde 0€",
            "h3": "Exactamente cuánto dinero hice con Dropshipping mes a mes siendo principiante",
            "h4": "Exactamente cuánto dinero gané con Dropshipping después de casi rendirme",
            "h5": "Exactamente cuánto dinero facturé haciendo Dropshipping sin saber lo que hacía",
            "h6": "Exactamente cuánto dinero me dejó Dropshipping en mis primeros 6 meses",
            "h7": "Exactamente cuánto dinero gané con Dropshipping antes de entender los datos",
            "h8": "Exactamente cuánto dinero facturé con Dropshipping durante mis primeros meses",
            "h9": "Exactamente cuánto dinero gané con Dropshipping cuando dejé de elegir productos a ojo",
            "h10": "Exactamente cuánto dinero hice con Dropshipping de octubre a marzo",
        }
        october = {
            "o1": "Octubre - 0€\nEmpecé con muchas ganas pero me quedé en parálisis por análisis pensando tanto cada paso que al final no lancé nada de verdad",
            "o2": "Octubre - 0€\nArranqué motivado aunque perdí demasiado tiempo con el logo y los colores sintiendo que trabajaba muchísimo mientras no avanzaba",
            "o3": "Octubre - 0€\nTenía todo montado en mi cabeza pero me daba miedo poner anuncios y perder dinero así que me bloqueé yo solo sin empezar",
            "o4": "Octubre - 0€\nMe metí con muchísimas ganas dudando de cada decisión y acabé con una tienda a medias y cero ventas después de semanas",
            "o5": "Octubre - 0€\nLancé mi primera tienda motivado, metí algo de dinero en anuncios y tuve visitas, pero nadie compró y perdí casi todo el presupuesto",
            "o6": "Octubre - 0€\nPensaba que tener la tienda publicada ya era avanzar, hasta que vi tráfico entrando y ni una sola persona pasando por caja",
        }
        november = {
            "n1": "Noviembre - 0€\nSeguí en cero intentando vender solo con contenido orgánico mientras veía a otros facturar y yo atascado en el mismo punto",
            "n2": "Noviembre - 0€\nQuise moverlo sin gastar mis ahorros pero el miedo a invertir me frenó y pasó otro mes entero sin que cambiara nada",
            "n3": "Noviembre - 0€\nLo peor fue ver a otros sacar ventas mientras yo seguía a cero y esa comparación constante me dejó bastante rallado la verdad",
            "n4": "Noviembre - 0€\nProbé un par de productos al azar sin que pegara ninguno y entendí que ir a ciegas no me iba a funcionar nunca",
            "n5": "Noviembre - 0€\nCambie fotos, textos y precios mil veces, pero el problema real era que seguía probando productos sin ningún criterio claro",
            "n6": "Noviembre - 0€\nMe convencí de que el fallo era el anuncio, luego la web y luego el precio, pero en realidad no sabía qué estaba vendiendo",
        }
        december = {
            "d1": "Diciembre - {amount}€\nLlegó la primera venta gracias al empujón de Navidad y pensé que ya había descubierto el secreto del ecommerce yo solo",
            "d2": "Diciembre - {amount}€\nEntró una venta pequeña por la locura navideña y me vine arriba creyendo que a partir de ahí todo sería igual de fácil",
            "d3": "Diciembre - {amount}€\nPor fin cayó la primera venta en Navidad y sentí que lo había pillado aunque me monté una película mucho más grande de la cuenta",
            "d4": "Diciembre - {amount}€\nLa primera venta me dio una motivación brutal, pero también me hizo confiarme demasiado rápido sin entender por qué había pasado",
            "d5": "Diciembre - {amount}€\nVendí algo por fin y durante dos días pensé que ya estaba dentro, hasta que miré los números reales y se me bajó la emoción",
        }
        january = {
            "j1": "Enero - 0€\nSe acabaron las fiestas y las ventas murieron por completo así que pagar Shopify para no facturar me dejó sin motivación real",
            "j2": "Enero - 0€\nVolví a cero en cuanto pasó Navidad y estuve a punto de dejarlo todo para buscar un trabajo normal y olvidarme del tema",
            "j3": "Enero - 0€\nEl golpe fue duro porque después de Navidad no entró nada y me frustraba seguir pagando la tienda sin ver ningún resultado",
            "j4": "Enero - 0€\nMe di cuenta de que una venta suelta no significaba tener un negocio y ese mes fue el que más cerca estuve de cerrarlo todo",
            "j5": "Enero - 0€\nSeguía entrando a mirar estadísticas cada rato, pero la tienda estaba muerta y yo ya no sabía qué tocar para arreglarla",
        }
        february = {
            "f1": "Febrero - {amount}€\nVi a un dropshipper usando Dropradar y me di una última oportunidad eligiendo productos por datos reales y no por intuición",
            "f2": "Febrero - {amount}€\nDescubrí Dropradar por otro chaval al que seguía y con una última bala guiada por métricas por fin empezaron a entrar ventas",
            "f3": "Febrero - {amount}€\nProbé Dropradar después de ver que otros sacaban productos con datos y al dejar de escoger por gusto personal la tienda arrancó",
            "f4": "Febrero - {amount}€\nEmpecé a usar Dropradar para mirar productos con señales reales y por primera vez sentí que no estaba apostando a ciegas",
            "f5": "Febrero - {amount}€\nDejé de elegir lo que a mí me gustaba, miré Dropradar con calma y las primeras ventas empezaron a tener sentido",
        }
        march = {
            "m1": "Marzo - {amount}€\nNo me hice millonario ni me compré un Ferrari pero por fin tenía ingresos estables y dejé de ir totalmente a ciegas cada semana",
            "m2": "Marzo - {amount}€\nNada de jets ni mansiones porque la diferencia real fue empezar a usar métricas de verdad y dejar de adivinar cada decisión",
            "m3": "Marzo - {amount}€\nNo vivo con lujos pero ya tenía ventas sólidas cada mes y aprendí que los datos mandan muchísimo más que la intuición",
            "m4": "Marzo - {amount}€\nNo fue una locura de dinero, pero ya podía explicar qué estaba funcionando y repetirlo sin sentir que todo dependía de suerte",
            "m5": "Marzo - {amount}€\nLa diferencia no fue hacerme rico, fue dejar de improvisar y tener un sistema que por fin me devolvía ventas con sentido",
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
        variants = {
            "a": {
                SlideRole.HOOK: "Exactly how much I made doing Dropshipping in these 6 months and why I almost quit...",
                SlideRole.OCTOBER: "October - $0\nI launched my first store feeling super motivated. I put some money into ads, got a lot of views, but nobody bought. It was a real reality check and I lost my budget.",
                SlideRole.NOVEMBER: "November - $0\nI paused the ads right away so I would not lose more money. I spent the whole month tweaking the store design and trying to get more organic traffic. Even so, I was still at 0 sales.",
                SlideRole.DECEMBER: "December - $0\nThe Christmas season passed me by. I watched everyone else making money while I stayed stuck, overthinking which product to launch because I was scared of getting it wrong again.",
                SlideRole.JANUARY: "January - $0\nI was not even opening Shopify anymore. I was frustrated about paying the monthly fee for nothing, and I was one click away from canceling my subscription. It felt like all of this was a waste of time.",
                SlideRole.FEBRUARY: "February - $800\nI saw a dropshipper I follow recommending Dropradar, and I decided to give it one last try. I picked a product strictly based on its metrics and, to my surprise, profitable sales started coming in.",
                SlideRole.MARCH: "March - $2700\nI finally have sales coming in consistently. I was close to giving up before learning that what really matters is consistency and knowing how to act on real metrics and data.",
            },
            "b": {
                SlideRole.HOOK: "Exactly how much I made in revenue in my first 6 months of Dropshipping and why I almost quit...",
                SlideRole.OCTOBER: "October - $0\nI started with a lot of excitement, but without really knowing anything. I spent the whole month building the website and looking for products that seemed good to me, but I did not get a single sale.",
                SlideRole.NOVEMBER: "November - $0\nIt frustrated me to see the weeks go by without making progress. I kept tweaking the store and watching tutorials, but I was scared to start ads and lose money, so I stayed stuck.",
                SlideRole.DECEMBER: "December - $0\nI watched everyone making money at Christmas while I stayed exactly the same. I felt unable to find a product that worked, and the pressure of seeing others succeed was burning me out.",
                SlideRole.JANUARY: "January - $0\nI was completely unmotivated. Paying the Shopify fee without selling anything felt like throwing money away, and I was one step away from closing the account and forgetting about everything.",
                SlideRole.FEBRUARY: "February - $680\nI saw a dropshipper I follow using Dropradar, and I decided to give it one last chance. I picked a product based on its data and metrics and, for the first time, I started selling for real.",
                SlideRole.MARCH: "March - $3100\nI am not a millionaire, but I finally have a business that works. I am glad I did not give up in January; the key was consistency and stopping the guessing game about which product would work.",
            },
        }
        return self._compose_type_1_fixed(language=Language.EN, variants=variants)
        hook_options = {
            "h1": "Exactly how much money I made with Dropshipping in my first 6 months",
            "h2": "Exactly how much I billed with Dropshipping starting from $0",
            "h3": "Exactly how much money Dropshipping made me month by month",
            "h4": "Exactly how much money I made with Dropshipping after almost quitting",
            "h5": "Exactly how much money I billed doing Dropshipping with zero experience",
            "h6": "Exactly how much money I kept from my first Dropshipping months",
            "h7": "Exactly how much money I really made with Dropshipping before data",
            "h8": "Exactly how much money I billed with Dropshipping in 6 months",
            "h9": "Exactly how much money I made with Dropshipping after I stopped guessing products",
            "h10": "Exactly how much money Dropshipping made me from October to March",
        }
        october = {
            "o1": "October - $0\nI started excited but got stuck in analysis paralysis overthinking every step and never really launching anything real",
            "o2": "October - $0\nI was motivated yet wasted way too much time on the logo and colors feeling busy while nothing actually moved",
            "o3": "October - $0\nEverything looked ready in my head but I was too scared to run ads and lose money so I just kept delaying the launch",
            "o4": "October - $0\nI jumped in with energy but doubted every decision and ended up with a half built store and zero sales after weeks",
            "o5": "October - $0\nI launched the first store motivated, put some money into ads and got visitors, but nobody bought and most of the budget disappeared",
            "o6": "October - $0\nI thought publishing the store meant progress until I saw traffic coming in and not one person going through checkout",
        }
        november = {
            "n1": "November - $0\nI stayed at zero trying to force organic sales while watching other people making money and feeling stuck in the same spot",
            "n2": "November - $0\nI wanted to avoid risking my savings so fear kept me frozen and another month passed with the exact same numbers",
            "n3": "November - $0\nThe worst part was seeing everyone else getting sales while I had nothing and that comparison really got into my head",
            "n4": "November - $0\nI tested a couple of random products without a single one landing and realized winging it was never going to work",
            "n5": "November - $0\nI changed photos, copy and prices again and again, but the real problem was still testing products without a clear reason",
            "n6": "November - $0\nFirst I blamed the ad, then the store and then the price, but honestly I did not know what I was really selling",
        }
        december = {
            "d1": "December - ${amount}\nMy first sale came in thanks to the Christmas push and I thought I had finally cracked ecommerce by myself",
            "d2": "December - ${amount}\nA small Christmas sale hit and I got carried away believing it would stay that easy from there on out",
            "d3": "December - ${amount}\nThat first sale during Christmas made me think I had figured it out and I got way too confident way too quickly",
            "d4": "December - ${amount}\nThe first sale gave me a crazy amount of motivation, but it also made me trust myself before I understood why it happened",
            "d5": "December - ${amount}\nI finally sold something and for two days thought I was in, until I checked the real numbers and calmed down fast",
        }
        january = {
            "j1": "January - $0\nThe holidays ended and sales completely died so paying Shopify for nothing was killing my motivation every single week",
            "j2": "January - $0\nAs soon as Christmas was over I went right back to zero and was close to quitting for a normal job and forgetting everything",
            "j3": "January - $0\nReality hit hard because after the holidays nothing came in and I hated paying for a store with no results at all",
            "j4": "January - $0\nI realized one random sale did not mean I had a business, and that was the month I got closest to shutting it all down",
            "j5": "January - $0\nI kept checking analytics every few hours, but the store was dead and I had no idea what to change next",
        }
        february = {
            "f1": "February - ${amount}\nI saw another dropshipper using Dropradar and gave myself one last shot picking products from real data and not gut",
            "f2": "February - ${amount}\nI found Dropradar through someone I followed and with one last try guided by metrics sales finally started to move",
            "f3": "February - ${amount}\nI tested Dropradar after seeing others rely on data and once I stopped choosing products by taste the store woke up",
            "f4": "February - ${amount}\nI started using Dropradar to check products with real signals and for once it did not feel like blind betting",
            "f5": "February - ${amount}\nI stopped picking what I personally liked, studied Dropradar calmly and the first sales finally made sense",
        }
        march = {
            "m1": "March - ${amount}\nI did not become a millionaire and did not buy a Ferrari but I finally had stable income and stopped guessing every single week",
            "m2": "March - ${amount}\nNo jets or mansions because the real change was using solid metrics instead of pure intuition in every single decision",
            "m3": "March - ${amount}\nI am not living some crazy luxury life but the income finally felt stable and I learned data beats guessing every time",
            "m4": "March - ${amount}\nIt was not insane money, but I could finally explain what was working and repeat it without feeling like it was luck",
            "m5": "March - ${amount}\nThe difference was not getting rich, it was having a system that finally turned tests into sales I could understand",
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
            social_choice_key=self._copy_choice_from_social_key(social_key),
        )

    def _compose_type_1_fixed(
        self,
        *,
        language: Language,
        variants: dict[str, dict[SlideRole, str]],
    ) -> ScriptPackage:
        choice_key = self._next_type_1_choice(language, variants)
        slides_by_role = dict(variants[choice_key])
        ordered = [slides_by_role[role] for role in TYPE_1_ROLES]
        social_key, social_copy = self._choose_social_copy(VideoType.TYPE_1, language)
        signature = _hash_signature([choice_key, *ordered, social_key])

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
            choice_key=choice_key,
            social_choice_key=self._copy_choice_from_social_key(social_key),
        )

    def _next_type_1_choice(
        self,
        language: Language,
        variants: dict[str, dict[SlideRole, str]],
    ) -> str:
        ordered_keys = list(variants)
        if not ordered_keys:
            raise RuntimeError("Tipo 1: no hay variantes configuradas.")
        last_choice = self.state.get_last_text_choice(VideoType.TYPE_1, language)
        if last_choice not in ordered_keys:
            return ordered_keys[0]
        next_index = (ordered_keys.index(last_choice) + 1) % len(ordered_keys)
        return ordered_keys[next_index]

    # ------------------------------------------------------------------
    # Type 2 — "4 things I wish I knew" tips
    # ------------------------------------------------------------------

    def _build_type_2_es(self) -> ScriptPackage:
        variants = {
            "a": {
                SlideRole.HOOK: "Habría pagado por saber estas 4 cosas cuando empecé con Dropshipping",
                SlideRole.TIP1: "1. Valida con poco presupuesto\nNo trates la publicidad como una apuesta. Invierte pequeñas sumas para testear qué anuncios funcionan y escala solo cuando los datos confirmen la rentabilidad.",
                SlideRole.TIP2: "2. Cuida al cliente tras el pago\nLa venta no termina cuando recibes el dinero. Un soporte rápido y amable evita reclamaciones bancarias y asegura la continuidad de tu cuenta.",
                SlideRole.TIP3: "3. Prioriza nichos sobre productos virales\nEvita la competencia saturada buscando soluciones para audiencias específicas. Usa Dropradar para validar productos con potencial y tener ventaja sobre tu competencia.",
                SlideRole.TIP4: "4. Proyecta profesionalidad y transparencia\nLa venta no termina cuando recibes el dinero. Un soporte rápido y amable evita reclamaciones bancarias y asegura la continuidad de tu cuenta.",
            },
            "b": {
                SlideRole.HOOK: "Errores que veo en pequeños Dropshippers que están empezando",
                SlideRole.TIP1: '1. Ten una tienda con aspecto "barato"\nSi tu web parece una plantilla de hace diez años, nadie confiará en ti. Añade reseñas, ofrece ofertas, sé sincero con los tiempos de envío e intenta reducirlos para conseguir ventas reales.',
                SlideRole.TIP2: "2. Trata los anuncios como una tragaperras\nNo lances dinero a Facebook o TikTok esperando un milagro. Empieza con poco, prueba diferentes enfoques y usa el contenido orgánico para ver qué funciona antes de invertir fuerte.",
                SlideRole.TIP3: "3. Vende lo mismo que todos\nLos productos virales tienen demasiada competencia y nulo margen. Busca nichos que resuelvan problemas reales y apóyate en herramientas como Dropradar para encontrar productos rentables.",
                SlideRole.TIP4: "4. Descuidar el trato con el comprador\nConseguir el pago es solo la mitad del trabajo. Si no ayudas al cliente tras la compra, tu reputación y tu cuenta bancaria lo pagarán. Una comunicación rápida evita devoluciones y protege tu negocio.",
            },
        }
        return self._compose_type_2_fixed(Language.ES, variants)

    def _build_type_2_en(self) -> ScriptPackage:
        variants = {
            "a": {
                SlideRole.HOOK: "I would have paid to know these 4 things when I started Dropshipping",
                SlideRole.TIP1: "1. Validate with a small budget\nDo not treat advertising like a bet. Invest small amounts to test which ads work and scale only when the data confirms profitability.",
                SlideRole.TIP2: "2. Take care of the customer after payment\nThe sale does not end when you receive the money. Fast, friendly support prevents bank claims and protects the continuity of your account.",
                SlideRole.TIP3: "3. Prioritize niches over viral products\nAvoid saturated competition by looking for solutions for specific audiences. Use Dropradar to validate products with potential and gain an advantage over your competition.",
                SlideRole.TIP4: "4. Project professionalism and transparency\nThe sale does not end when you receive the money. Fast, friendly support prevents bank claims and protects the continuity of your account.",
            },
            "b": {
                SlideRole.HOOK: "Mistakes I see small Dropshippers making when they are starting out",
                SlideRole.TIP1: "1. Having a cheap looking store\nIf your website looks like a template from ten years ago, nobody will trust you. Add reviews, offer deals, be honest about shipping times and try to reduce them to get real sales.",
                SlideRole.TIP2: "2. Treating ads like a slot machine\nDo not throw money at Facebook or TikTok hoping for a miracle. Start small, test different angles and use organic content to see what works before investing heavily.",
                SlideRole.TIP3: "3. Selling the same thing as everyone else\nViral products have too much competition and no margin. Look for niches that solve real problems and lean on tools like Dropradar to find profitable products.",
                SlideRole.TIP4: "4. Neglecting the buyer experience\nGetting the payment is only half the job. If you do not help the customer after purchase, your reputation and your bank account will pay for it. Fast communication prevents refunds and protects your business.",
            },
        }
        return self._compose_type_2_fixed(Language.EN, variants)

    def _compose_type_2_fixed(
        self,
        language: Language,
        variants: dict[str, dict[SlideRole, str]],
    ) -> ScriptPackage:
        choice_key = self._next_type_2_choice(language, variants)
        slides_by_role = dict(variants[choice_key])
        social_key, social_copy = self._choose_social_copy(VideoType.TYPE_2, language)
        ordered = [slides_by_role[role] for role in TYPE_2_ROLES]
        self._assert_type_2_rules(slides_by_role)
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=_hash_signature([choice_key, *ordered, social_key]),
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
            choice_key=choice_key,
            social_choice_key=self._copy_choice_from_social_key(social_key),
        )

    def _next_type_2_choice(
        self,
        language: Language,
        variants: dict[str, dict[SlideRole, str]],
    ) -> str:
        ordered_keys = list(variants)
        if not ordered_keys:
            raise RuntimeError("Tipo 2: no hay variantes configuradas.")
        last_choice = self.state.get_last_text_choice(VideoType.TYPE_2, language)
        if last_choice not in ordered_keys:
            return ordered_keys[0]
        next_index = (ordered_keys.index(last_choice) + 1) % len(ordered_keys)
        return ordered_keys[next_index]

    @staticmethod
    def _assert_type_2_rules(slides_by_role: dict[SlideRole, str]) -> None:
        for role, slide in slides_by_role.items():
            for token in FORBIDDEN_TYPE_2_TOKENS:
                if token in slide:
                    raise ValueError(
                        f"Tipo 2 ({role.value}): el texto contiene el carácter prohibido '{token}'."
                    )
            if role != SlideRole.HOOK and "\n" not in slide:
                raise ValueError(
                    f"Tipo 2 ({role.value}): el consejo debe separar título y texto."
                )
        if "Dropradar" not in slides_by_role.get(SlideRole.TIP3, ""):
            raise ValueError("Tipo 2: el consejo 3 debe mencionar Dropradar.")
        hook = slides_by_role.get(SlideRole.HOOK, "")
        if "Dropshipping" not in hook and "Dropshippers" not in hook:
            raise ValueError("Tipo 2: el hook debe mencionar Dropshipping o Dropshippers.")

    # ------------------------------------------------------------------
    # Type 3 — one hook photo + fixed tool stack
    # ------------------------------------------------------------------

    def _build_type_3_es(self) -> ScriptPackage:
        hooks = {
            "h1": "Como empezar en Dropshipping en 2026",
            "h2": "Como hacer Dropshipping en 2026",
            "h3": "Empieza",
        }
        payment_tool = random.choice(("PayPal", "Stripe"))
        marketing_tool = random.choice(("Instagram", "TikTok"))
        tools = {
            SlideRole.TOOL_STORE: "1. Tienda\nConstruye tu tienda por solo 1€ - Usa Shopify",
            SlideRole.TOOL_PRODUCT_SEARCH: "2. Busqueda de productos\nEncuentra productos ganadores - Usa Dropradar",
            SlideRole.TOOL_SCRIPTS: "3. Guiones\nSigue guiones para tus videos - Usa ChatGPT",
            SlideRole.TOOL_PAYMENTS: f"4. Pagos\nGestiona tus pagos de forma segura - Usa {payment_tool}",
            SlideRole.TOOL_EDITING: "5. Edicion\nEdita tus videos para mas calidad - Usa CapCut",
            SlideRole.TOOL_MARKETING: f"6. Marketing\nPromocionate organicamente - Usa {marketing_tool}",
        }
        return self._compose_type_3(Language.ES, hooks, tools)

    def _build_type_3_en(self) -> ScriptPackage:
        hooks = {
            "h1": "How to start Dropshipping in 2026",
            "h2": "How to do Dropshipping in 2026",
            "h3": "Start",
        }
        payment_tool = random.choice(("PayPal", "Stripe"))
        marketing_tool = random.choice(("Instagram", "TikTok"))
        tools = {
            SlideRole.TOOL_STORE: "1. Store\nBuild your store for only $1 - Use Shopify",
            SlideRole.TOOL_PRODUCT_SEARCH: "2. Product Search\nFind winning products - Use Dropradar",
            SlideRole.TOOL_SCRIPTS: "3. Scripts\nFollow scripts for your videos - Use ChatGPT",
            SlideRole.TOOL_PAYMENTS: f"4. Payments\nManage your payments securely - Use {payment_tool}",
            SlideRole.TOOL_EDITING: "5. Editing\nEdit your videos for better quality - Use CapCut",
            SlideRole.TOOL_MARKETING: f"6. Marketing\nPromote your product organically - Use {marketing_tool}",
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
            social_choice_key=self._copy_choice_from_social_key(social_key),
        )

    def _choose_social_copy(
        self,
        video_type: VideoType,
        language: Language,
    ) -> tuple[str, SocialCopy]:
        variants = self._social_copy_variants(video_type, language)
        copy_key = self._next_social_copy_choice(video_type, language, variants)
        fallback_title, description, hashtags = variants[copy_key]
        title_variants = self._social_title_variants(video_type, language)
        if title_variants:
            title_key = random.choice(list(title_variants))
            title = title_variants[title_key]
        else:
            title_key = "default"
            title = fallback_title
        return f"{copy_key}:{title_key}", SocialCopy(
            title=title,
            description=description,
            hashtags=hashtags,
        )

    @staticmethod
    def _copy_choice_from_social_key(social_key: str) -> str:
        return social_key.split(":", 1)[0]

    def _next_social_copy_choice(
        self,
        video_type: VideoType,
        language: Language,
        variants: dict[str, tuple[str, str, list[str]]],
    ) -> str:
        ordered_keys = list(variants)
        if not ordered_keys:
            raise RuntimeError("No hay variantes de copy social configuradas.")
        last_choice = self.state.get_last_social_choice(video_type, language)
        if last_choice not in ordered_keys:
            return ordered_keys[0]
        next_index = (ordered_keys.index(last_choice) + 1) % len(ordered_keys)
        return ordered_keys[next_index]

    def _social_copy_variants(
        self,
        video_type: VideoType,
        language: Language,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if language == Language.EN:
            variants = self._social_copy_variants_en(video_type)
        else:
            variants = self._social_copy_variants_es(video_type)
        return self._prepare_social_copy_variants(video_type, language, variants)

    def _social_title_variants(
        self,
        video_type: VideoType,
        language: Language,
    ) -> dict[str, str]:
        if language == Language.EN:
            return self._social_title_variants_en(video_type)
        return self._social_title_variants_es(video_type)

    def _social_title_variants_es(self, video_type: VideoType) -> dict[str, str]:
        if video_type == VideoType.TYPE_1:
            return {
                "t1": "Lo que facture cuando deje de adivinar",
                "t2": "Mi cambio real con dropshipping",
                "t3": "De perder meses a entender los numeros",
                "t4": "La parte que nadie me explico al empezar",
                "t5": "Cuanto hice cuando empece a usar datos",
                "t6": "El mes donde todo empezo a tener sentido",
                "t7": "Lo que habria querido saber antes",
                "t8": "Mi progreso real montando una tienda online",
                "t9": "De probar al azar a vender con criterio",
                "t10": "Asi cambio mi tienda en 6 meses",
                "t11": "El error que me estaba costando dinero",
                "t12": "La diferencia entre intentarlo y medirlo",
            }
        if video_type == VideoType.TYPE_2:
            return {
                "t1": "Antes de gastar mas dinero mira esto",
                "t2": "4 errores que frenan una tienda online",
                "t3": "La revision que haria antes de vender",
                "t4": "Si haces dropshipping revisa esto",
                "t5": "Lo que miraria antes de lanzar anuncios",
                "t6": "4 puntos que pueden salvar tu presupuesto",
                "t7": "La base que casi nadie revisa al empezar",
                "t8": "Esto separa una tienda floja de una seria",
                "t9": "Antes de buscar otro producto arregla esto",
                "t10": "Los detalles que te hacen perder ventas",
                "t11": "Una checklist rapida para tu tienda",
                "t12": "Si no vendes revisa estas 4 cosas",
            }
        return {
            "t1": "Herramientas simples para empezar en 2026",
            "t2": "El stack que usaria para lanzar una tienda",
            "t3": "Tu base para empezar dropshipping",
            "t4": "6 herramientas para no complicarte al empezar",
            "t5": "La ruta simple para montar tu primera tienda",
            "t6": "Empieza con estas herramientas y valida rapido",
            "t7": "Lo minimo que necesitas para probar una tienda",
            "t8": "Un stack limpio para vender online",
            "t9": "De idea a tienda con herramientas simples",
            "t10": "La base practica para empezar dropshipping",
            "t11": "Herramientas que si usaria al empezar",
            "t12": "Ordena tu tienda antes de complicarte",
        }

    def _social_title_variants_en(self, video_type: VideoType) -> dict[str, str]:
        if video_type == VideoType.TYPE_1:
            return {
                "t1": "What changed when I stopped guessing",
                "t2": "My real dropshipping progress",
                "t3": "From random tests to clearer numbers",
                "t4": "The part I wish I knew earlier",
                "t5": "How my store changed in 6 months",
                "t6": "The month dropshipping started making sense",
                "t7": "The mistake that kept costing me money",
                "t8": "What helped me read the numbers better",
                "t9": "From almost quitting to a real process",
                "t10": "The shift that made my tests useful",
                "t11": "What I learned after months of trying",
                "t12": "The difference between guessing and measuring",
            }
        if video_type == VideoType.TYPE_2:
            return {
                "t1": "Check this before spending more",
                "t2": "4 mistakes that slow down online stores",
                "t3": "The review I would do before selling",
                "t4": "If you dropship, check these first",
                "t5": "Before running ads, look at this",
                "t6": "4 points that can save your budget",
                "t7": "The base most beginners skip",
                "t8": "What separates weak stores from solid ones",
                "t9": "Fix this before testing another product",
                "t10": "Small details that cost sales",
                "t11": "A quick checklist for your store",
                "t12": "If sales are slow, review these 4 things",
            }
        return {
            "t1": "Simple tools to start in 2026",
            "t2": "The stack I would use to launch a store",
            "t3": "Your base for starting dropshipping",
            "t4": "6 tools to keep the start simple",
            "t5": "The simple route for your first store",
            "t6": "Start with these tools and validate faster",
            "t7": "The minimum setup for testing a store",
            "t8": "A clean stack for selling online",
            "t9": "From idea to store with simple tools",
            "t10": "A practical base for dropshipping",
            "t11": "Tools I would actually use at the start",
            "t12": "Organize your store before overcomplicating it",
        }

    def _prepare_social_copy_variants(
        self,
        video_type: VideoType,
        language: Language,
        variants: dict[str, tuple[str, str, list[str]]],
    ) -> dict[str, tuple[str, str, list[str]]]:
        expansions = self._social_description_expansions(video_type, language)
        fallback = self._social_description_fallback(video_type, language)
        prepared: dict[str, tuple[str, str, list[str]]] = {}
        for index, (key, (title, description, hashtags)) in enumerate(list(variants.items())[:4]):
            expanded = f"{description} {expansions[index % len(expansions)]}".strip()
            while len(expanded) < SOCIAL_DESCRIPTION_TARGET_MIN:
                expanded = f"{expanded} {fallback}".strip()
            if len(expanded) > SOCIAL_DESCRIPTION_TARGET_MAX:
                expanded = expanded[:SOCIAL_DESCRIPTION_TARGET_MAX].rsplit(" ", 1)[0].rstrip(",.") + "."
            prepared[key] = (title, expanded, hashtags)
        return prepared

    def _social_description_expansions(
        self,
        video_type: VideoType,
        language: Language,
    ) -> tuple[str, ...]:
        if language == Language.EN:
            return self._social_description_expansions_en(video_type)
        return self._social_description_expansions_es(video_type)

    def _social_description_expansions_es(self, video_type: VideoType) -> tuple[str, ...]:
        if video_type == VideoType.TYPE_1:
            return (
                "La parte importante no es copiar mis cifras ni esperar que tu primer mes se parezca al mío. Lo importante es entender la secuencia. Primero viene la ilusión, luego aparece el choque con la realidad, después empiezas a distinguir entre estar ocupado y estar tomando mejores decisiones. Si solo miras el resultado final, parece que todo cambió de golpe, pero por dentro fue mucho más lento: revisar por qué un producto no se vendió, mirar si el anuncio atraía curiosos o compradores, comprobar si la tienda generaba confianza y aceptar que algunos tests tenían que cerrarse aunque me hubiera encariñado con la idea. Esa disciplina es menos emocionante que enseñar capturas, pero es la que evita repetir el mismo error durante meses. Si estás en una etapa parecida, usa este contenido como una pausa para ordenar tu propio proceso. Escribe qué estás probando, qué métrica estás mirando y qué decisión vas a tomar si los datos salen mal. Cuando haces eso, incluso una semana floja empieza a darte información útil.",
                "Lo que más me costó aprender fue dejar de buscar una señal perfecta antes de actuar. Quería garantías, quería que alguien me dijera qué producto lanzar, cuánto invertir y cuándo escalar, pero el ecommerce no funciona con esa claridad desde el primer día. Funciona con hipótesis pequeñas, pruebas controladas y ajustes que se acumulan. Por eso esta historia no va de hacerse rico rápido, va de sobrevivir a la parte confusa sin convertir cada fallo en una prueba de que no sirves. Si un producto no convierte, quizá el ángulo está mal. Si la gente hace clic pero no compra, quizá la tienda no sostiene la promesa del anuncio. Si nadie guarda el contenido, quizá el problema no es el algoritmo sino la oferta. Separar esas piezas me ayudó a respirar y a decidir con más calma. Guarda este post si necesitas recordar que avanzar no siempre se siente como avanzar mientras lo estás viviendo.",
                "También hay algo que casi nadie dice: los meses malos suelen ser caros porque mezclan emoción con prisa. Cuando estás frustrado, cambias de producto demasiado rápido, tocas la tienda sin una razón clara, compras herramientas nuevas para sentir que estás haciendo algo y terminas más disperso que antes. El cambio real empezó cuando limité las decisiones. Un producto cada vez, una hipótesis clara, una métrica principal y un periodo suficiente para leer resultados. Eso no hace que todo funcione, pero reduce el caos y te permite distinguir un mal producto de una mala ejecución. En dropshipping, esa diferencia vale mucho. Si hoy estás probando sin estructura, no necesitas motivarte más: necesitas bajar el ruido, definir el criterio y dejar que los datos te digan qué parte corregir primero.",
                "No tomes este carrusel como una promesa, tómalo como un mapa de errores comunes. La mayoría de principiantes abandona porque interpreta el silencio del mercado como un juicio personal, cuando muchas veces solo es feedback mal leído. Nadie compra porque el producto no queda claro, porque la oferta no justifica el precio, porque la web genera dudas o porque el contenido atrae a gente que mira pero no tiene intención de pagar. Cuando empiezas a nombrar el problema con precisión, dejas de sentir que todo está roto a la vez. Ahí aparece el progreso real: no en acertar siempre, sino en saber qué cambiar después de cada intento. Esa es la mentalidad que me habría ahorrado más tiempo al principio.",
            )
        if video_type == VideoType.TYPE_2:
            return (
                "La razón por la que estos cuatro puntos importan tanto es que funcionan como una prueba de presión antes de meter tráfico. Una tienda puede verse bonita en una captura y aun así romperse cuando llegan compradores reales: el margen se queda corto, la promesa del anuncio no coincide con la página, las dudas de envío aparecen demasiado tarde y el soporte se improvisa cuando ya hay dinero de por medio. Revisar esto antes no es perder tiempo, es comprar claridad. Si detectas un problema en cualquiera de las cuatro áreas, no lo tapes con más presupuesto. Corrígelo, vuelve a mirar la experiencia como si fueras cliente y pregúntate si tú comprarías sin conocer la marca. Esa pregunta incomoda, pero suele enseñar más que otra tarde mirando videos de tácticas.",
                "Piensa en esta checklist como un filtro para tomar mejores decisiones, no como una lista decorativa. Si el margen real no aguanta, cualquier venta puede convertirse en un problema. Si la tienda no inspira confianza, el tráfico solo hará más visible la debilidad. Si el producto no resuelve un dolor concreto, el anuncio tendrá que exagerar para llamar la atención. Y si el soporte no está preparado, la primera duda del cliente puede transformarse en una devolución. Lo bueno es que estas áreas se pueden trabajar antes de gastar fuerte. Puedes recalcular precios, mejorar pruebas sociales, comparar productos con datos y preparar respuestas básicas. No es glamuroso, pero es exactamente lo que separa una prueba seria de una apuesta.",
                "Muchos principiantes creen que el problema siempre está en el anuncio porque es la parte más visible. Pero un anuncio solo trae gente; no arregla márgenes, no construye confianza por ti y no convierte un producto débil en una oferta sólida. Antes de culpar al creativo, mira el recorrido completo. Qué ve la persona al entrar, qué dudas aparecen, qué promesa le hiciste, cuánto tarda en entender el beneficio y qué pasa después del pago. Cuando haces esa revisión, encuentras fugas que estaban escondidas a plena vista. A veces el ajuste no es cambiar todo, sino ordenar lo básico para que el tráfico tenga una oportunidad real de convertirse.",
                "La ventaja de revisar estos puntos es que te obliga a pensar como negocio y no solo como creador de anuncios. Un negocio necesita margen, confianza, demanda y una experiencia mínima que no destruya lo que vendiste. Si falta una pieza, lo notarás tarde o temprano, normalmente cuando ya has gastado tiempo o dinero. Por eso conviene parar antes de escalar y hacer una auditoría honesta. No busques perfección; busca que nada importante esté roto. Una tienda simple pero clara suele ser más fuerte que una tienda cargada de trucos que no responde a las preguntas básicas del comprador.",
            )
        return (
            "La clave de este stack no es que cada herramienta sea la única opción posible, sino que cada una cumple un trabajo concreto dentro del flujo. Shopify te da la base para vender, Dropradar te ayuda a investigar con datos, ChatGPT acelera guiones y ángulos, PayPal o Stripe reducen fricción en el cobro, CapCut mantiene la producción de contenido ligera e Instagram o TikTok te dan un lugar donde practicar la respuesta del mercado. Cuando entiendes el papel de cada herramienta, dejas de coleccionar apps y empiezas a construir una rutina. Esa rutina es lo que importa al principio: publicar, medir, ajustar y volver a probar sin convertir cada decisión en una semana de dudas.",
            "Empezar con pocas herramientas también protege tu atención. Al principio es muy fácil pensar que el siguiente plugin, plantilla o software va a resolver la falta de ventas, pero casi siempre el bloqueo está en otro sitio: no has validado bien el producto, no publicas contenido suficiente, no sabes qué dato mirar o cambias de idea antes de terminar una prueba. Un stack simple te obliga a mirar lo esencial. Qué vendes, por qué alguien lo compraría, cómo lo explicas, cómo cobras y cómo generas tráfico. Si esas preguntas no están claras, añadir más herramientas solo hace que el problema parezca más profesional, pero no más resuelto.",
            "Usa esta lista como punto de partida, no como jaula. Puedes cambiar una herramienta por otra si ya tienes experiencia, pero evita romper el orden. Primero una tienda funcional, luego producto, luego contenido, después pagos, edición y distribución. Ese orden mantiene el proyecto en movimiento porque cada pieza prepara la siguiente. Si intentas optimizar todo antes de publicar, vas a sentir que trabajas mucho sin recibir feedback real. En cambio, si montas una base suficiente y sales a probar, el mercado empieza a responder. Algunas respuestas serán incómodas, pero al menos sabrás qué ajustar con datos y no solo con intuición.",
            "El error más común es confundir empezar simple con empezar descuidado. Simple significa que cada pieza tiene una función clara y que puedes repetir el proceso sin depender de una configuración enorme. Descuidado significa lanzar sin entender márgenes, sin revisar la tienda, sin preparar contenido y sin medir nada. Este stack busca lo primero. Te da una estructura ligera para moverte rápido, pero también te recuerda que cada herramienta necesita uso real. No sirve tener Shopify si no mejoras la oferta, ni Dropradar si ignoras los datos, ni ChatGPT si no publicas, ni CapCut si nunca pruebas formatos distintos. La herramienta solo vale cuando entra en una rutina.",
        )

    def _social_description_expansions_en(self, video_type: VideoType) -> tuple[str, ...]:
        if video_type == VideoType.TYPE_1:
            return (
                "The important part is not copying my numbers or expecting your first month to look like mine. The important part is understanding the sequence. First comes motivation, then the reality check, and then the slow skill of separating busy work from better decisions. If you only look at the final result, it seems like everything changed at once, but inside the process it was much slower: checking why a product did not sell, asking whether the ad attracted viewers or buyers, seeing if the store created trust and accepting that some tests had to be closed even when I liked the idea. That discipline is less exciting than showing screenshots, but it keeps you from repeating the same mistake for months. If you are in a similar stage, use this as a pause to organize your own process. Write down what you are testing, which metric matters and what you will change if the data comes back weak.",
                "What took me the longest to learn was to stop waiting for a perfect signal before acting. I wanted guarantees, I wanted someone to tell me which product to launch, how much to spend and when to scale, but ecommerce does not start with that kind of clarity. It starts with small hypotheses, controlled tests and adjustments that compound. This story is not about getting rich quickly, it is about surviving the confusing part without treating every failed test as proof that you are not built for it. If a product does not convert, maybe the angle is wrong. If people click but do not buy, maybe the store does not support the promise. If nobody saves the content, maybe the problem is not the algorithm but the offer. Separating those pieces made the work calmer and more useful.",
                "There is also a part almost nobody says clearly: bad months become expensive when emotion and urgency mix together. When you are frustrated, you switch products too fast, edit the store without a clear reason, buy new tools to feel productive and end up more scattered than before. The real change started when I limited the decisions. One product at a time, one clear hypothesis, one main metric and enough time to read the result. That does not make everything work, but it reduces the chaos and helps you tell the difference between a bad product and weak execution. In dropshipping, that difference matters a lot. If you are testing without structure, you may not need more motivation. You may need less noise and a clearer reason for the next move.",
                "Do not read this carousel as a promise. Read it as a map of common mistakes. Most beginners quit because they treat silence from the market like a personal verdict, when it is often just feedback they have not learned to read yet. People may not buy because the product is unclear, because the offer does not justify the price, because the store creates doubt or because the content attracts people who watch but never intended to pay. When you name the problem more precisely, the whole project stops feeling broken at once. That is where real progress begins: not in always being right, but in knowing what to change after each attempt.",
            )
        if video_type == VideoType.TYPE_2:
            return (
                "These four points matter because they work like a pressure test before you send traffic. A store can look good in a screenshot and still break when real buyers arrive: the margin is too thin, the ad promise does not match the page, shipping doubts appear too late and support is improvised after money has already changed hands. Reviewing this first is not wasted time, it is clarity. If one of the four areas is weak, do not hide it under a bigger budget. Fix it, look at the experience like a customer and ask whether you would buy from the brand without knowing who is behind it. That question is uncomfortable, but it usually teaches more than another afternoon watching tactics.",
                "Treat this checklist as a filter for better decisions, not as a decorative list. If the real margin does not hold, every sale can become a problem. If the store does not create trust, traffic only makes the weakness more visible. If the product does not solve a concrete problem, the ad has to exaggerate to get attention. And if support is not prepared, the first customer question can become a refund. The good news is that these areas can be improved before spending heavily. You can recalculate prices, improve social proof, compare products with data and prepare basic answers. It is not glamorous, but it is exactly what separates a serious test from a guess.",
                "Many beginners assume the problem is always the ad because that is the most visible part. But an ad only brings people in; it does not fix margins, create trust for you or turn a weak product into a strong offer. Before blaming the creative, look at the whole path. What does the buyer see first, which doubts appear, what promise did you make, how quickly is the benefit clear and what happens after payment? When you review the full journey, you find leaks that were hiding in plain sight. Sometimes the answer is not changing everything. Sometimes it is making the basics solid enough for traffic to have a real chance.",
                "The value of these checks is that they force you to think like a business, not only like someone making ads. A business needs margin, trust, demand and a minimum customer experience that does not destroy the sale after checkout. If one piece is missing, you will feel it sooner or later, usually after spending time or money. That is why it helps to pause before scaling and run an honest audit. Do not look for perfection; look for nothing important being obviously broken. A simple store with a clear offer is often stronger than a store full of tricks that cannot answer the buyer's basic questions.",
            )
        return (
            "The value of this stack is not that every tool is the only possible option, but that each one has a clear job inside the workflow. Shopify gives you the selling base, Dropradar helps with product research, ChatGPT speeds up scripts and angles, PayPal or Stripe reduce payment friction, CapCut keeps content production light and Instagram or TikTok give you a place to practice market response. When you understand the role of each tool, you stop collecting apps and start building a routine. That routine is what matters at the beginning: publish, measure, adjust and test again without turning every decision into another week of doubt.",
            "Starting with fewer tools also protects your attention. It is easy to believe the next plugin, template or software will solve the lack of sales, but the real block is usually somewhere else: the product was not validated, you are not posting enough content, you do not know which metric to watch or you change ideas before finishing a test. A simple stack forces you to look at the essentials. What are you selling, why would someone buy it, how do you explain it, how do you take payment and how do you get traffic? If those questions are unclear, adding more tools only makes the problem look more professional, not more solved.",
            "Use this list as a starting point, not as a cage. You can swap one tool for another if you already know what you are doing, but avoid breaking the order. First a functional store, then product research, then content, then payments, editing and distribution. That order keeps the project moving because each piece prepares the next one. If you try to optimize everything before publishing, you can work for weeks without real feedback. If you build a good enough base and start testing, the market starts answering. Some answers will be uncomfortable, but at least you will know what to adjust with data instead of pure instinct.",
            "The most common mistake is confusing simple with careless. Simple means every piece has a clear function and you can repeat the process without depending on a huge setup. Careless means launching without understanding margins, without reviewing the store, without preparing content and without measuring anything. This stack is aiming for the first version. It gives you a light structure to move fast, while reminding you that every tool needs real use. Shopify means little if you never improve the offer, Dropradar means little if you ignore the data, ChatGPT means little if you do not publish and CapCut means little if you never test new formats.",
        )

    def _social_description_fallback(
        self,
        video_type: VideoType,
        language: Language,
    ) -> str:
        if language == Language.EN:
            if video_type == VideoType.TYPE_1:
                return "Keep the focus on the process, not on the fantasy of a perfect result. One clear test, one useful metric and one honest adjustment can teach more than another week of random changes."
            if video_type == VideoType.TYPE_2:
                return "Use it as a quick audit before spending more. The goal is not to make the store perfect, but to remove the obvious leaks before traffic makes them expensive."
            return "Keep the setup simple enough to repeat. The tools only matter when they help you publish, measure and improve with less friction every week."
        if video_type == VideoType.TYPE_1:
            return "Quédate con el proceso, no con la fantasía de un resultado perfecto. Una prueba clara, una métrica útil y un ajuste honesto enseñan más que otra semana de cambios aleatorios."
        if video_type == VideoType.TYPE_2:
            return "Úsalo como auditoría rápida antes de gastar más. La meta no es tener una tienda perfecta, sino quitar las fugas evidentes antes de que el tráfico las vuelva caras."
        return "Mantén el sistema lo bastante simple como para repetirlo. Las herramientas importan cuando te ayudan a publicar, medir y mejorar con menos fricción cada semana."

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
                "es5": (
                    "Cuanto facture realmente con dropshipping",
                    "Este carrusel resume una parte que casi nunca se cuenta con calma, los meses donde abres la tienda, te ilusionas con cada visita y aun así no entra dinero suficiente para justificar todo el esfuerzo. Al principio yo confundía movimiento con progreso, tocar la web, cambiar textos, mirar productos y revisar estadísticas cada rato me hacía sentir ocupado, pero no me acercaba a una decisión mejor. La diferencia llegó cuando dejé de buscar el producto perfecto por intuición y empecé a mirar datos con más humildad, demanda, anuncios que ya estaban funcionando, margen y señales reales de compra. Dropradar no convirtió el proceso en magia, pero sí me dio una forma más ordenada de filtrar antes de gastar. Eso cambió mi cabeza más que mis números al principio, porque cada prueba dejó de ser una apuesta emocional y empezó a ser una decisión que podía entender. Si estás en esa fase rara de trabajar mucho y facturar poco, quizá no te falta motivación, quizá te falta un criterio más limpio para elegir qué probar.",
                    ["#dropshipping", "#facturacion", "#ecommerce", "#productresearch", "#dropradar"],
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
                "es5": (
                    "Antes de gastar mas en tu tienda",
                    "Antes de meter más dinero en anuncios, revisa si la base de la tienda tiene sentido de verdad. Muchas veces el problema no es que falte presupuesto, es que estás empujando tráfico hacia una estructura que todavía no está preparada para convertir. Si el margen real no aguanta comisiones, devoluciones y coste de adquisición, cada venta puede parecer buena en pantalla y seguir siendo mala para tu bolsillo. Si la web no transmite confianza, el cliente se va antes de leer tu oferta. Si eliges productos por intuición, cada prueba se parece demasiado a una apuesta. Y si después del pago no hay soporte claro, cualquier duda puede terminar en reembolso o disputa. Estas cuatro partes no son espectaculares, pero son las que hacen que una tienda sobreviva cuando empieza a llegar tráfico real. Guárdalo como una revisión rápida para no seguir arreglando solo el anuncio cuando la fuga quizá está mucho antes.",
                    ["#dropshippingtips", "#tiendaonline", "#marketingdigital", "#ecommerce", "#dropradar"],
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
            "es5": (
                "El stack limpio para empezar",
                "Si quieres empezar dropshipping sin llenar tu navegador de herramientas que no entiendes, usa una base simple y céntrate en validar. Primero necesitas una tienda que puedas enseñar sin vergüenza, después una forma de elegir productos con datos y no solo por gusto personal, luego guiones que puedas convertir en contenido rápido, pagos preparados para no improvisar cuando llegue el primer pedido, una herramienta de edición que no te frene y un canal orgánico donde publicar con constancia. Lo importante no es tener el sistema más caro, es tener un flujo que puedas repetir durante varias semanas sin bloquearte. Cuando cada herramienta cumple un papel claro, dejas de saltar de app en app buscando una ventaja secreta y empiezas a aprender del mercado real. Guarda esta lista y vuelve a ella cada vez que sientas que estás complicando demasiado algo que todavía necesita pruebas simples.",
                ["#dropshipping2026", "#herramientas", "#shopify", "#capcut", "#dropradar"],
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
                "en5": (
                    "How much I really billed dropshipping",
                    "This carousel is about the part that rarely looks clean while you are living it, opening the store, getting excited about every visitor and still not making enough money to justify the hours. At first I confused movement with progress. Changing the site, rewriting copy, scrolling products and checking analytics made me feel busy, but it did not make my decisions any better. The shift came when I stopped chasing products by instinct and started looking at cleaner signals, demand, working ads, margin and real buying intent. Dropradar did not make the process magic, but it gave me a calmer way to filter before spending. That changed my mindset before it changed the numbers, because every test stopped feeling like an emotional bet and became something I could explain. If you are working hard but billing very little, the missing piece might not be motivation. It might be a better reason for choosing what to test next.",
                    ["#dropshipping", "#ecommercejourney", "#productresearch", "#onlineincome", "#dropradar"],
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
                "en5": (
                    "Check this before spending more",
                    "Before putting more money into ads, check whether the base of the store actually makes sense. A lot of the time the problem is not a lack of budget, it is sending traffic into a setup that is not ready to convert. If the real margin cannot survive fees, refunds and acquisition cost, every order can look good on the dashboard and still be bad for your pocket. If the website does not build trust, the buyer leaves before the offer has a chance. If the product was chosen on instinct, every test becomes too close to a gamble. And if support is unclear after payment, a simple question can become a refund or dispute. These four areas are not flashy, but they are what help a store survive when real traffic arrives. Save this as a quick review before blaming only the creative again.",
                    ["#dropshippingtips", "#shopifystore", "#ecommerce", "#digitalmarketing", "#dropradar"],
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
            "en5": (
                "A clean stack to start",
                "If you want to start dropshipping without filling your browser with tools you barely understand, keep the base simple and focus on validation. First you need a store you can show without feeling embarrassed, then a product research flow based on data instead of personal taste, then scripts you can turn into content quickly, payments ready before the first order arrives, an editing tool that does not slow you down and an organic channel where you can practice consistently. The point is not having the most expensive system, it is having a workflow you can repeat for several weeks without freezing. When every tool has one clear job, you stop jumping from app to app looking for a secret advantage and start learning from the real market. Save this list and come back to it whenever you feel like you are making the first steps harder than they need to be.",
                ["#dropshipping2026", "#ecommercetools", "#shopify", "#capcut", "#dropradar"],
            ),
        }

    @staticmethod
    def _assert_type_3_rules(slides_by_role: dict[SlideRole, str]) -> None:
        full_text = "\n".join(slides_by_role.values()).lower()
        if "hosting" in full_text or "hostinger" in full_text:
            raise ValueError("Tipo 3: hosting no debe aparecer.")
        if not slides_by_role.get(SlideRole.HOOK, "").strip():
            raise ValueError("Tipo 3: el hook no puede ir vacio.")
        ScriptGenerator._assert_one_tool(
            slides_by_role,
            SlideRole.TOOL_PAYMENTS,
            ("paypal", "stripe"),
            "pagos",
        )
        ScriptGenerator._assert_one_tool(
            slides_by_role,
            SlideRole.TOOL_EDITING,
            ("capcut",),
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

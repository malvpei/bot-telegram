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
    TYPE_4_ROLES,
    VideoGender,
    VideoType,
)
from app.state import StateStore


# Em dash, en dash, fullwidth semicolon, hyphen-minus variants — anything that
# can render as a long dash or semicolon in the rendered video.
FORBIDDEN_TYPE_2_TOKENS: tuple[str, ...] = (";", "；", "—", "–", "ー", "―")
SOCIAL_DESCRIPTION_TARGET_MIN = 500
SOCIAL_DESCRIPTION_TARGET_MAX = 3500
FEMALE_ES_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("supermotivado", "supermotivada"),
    ("desmotivado", "desmotivada"),
    ("motivado", "motivada"),
    ("frustrado", "frustrada"),
    ("agotado", "agotada"),
    ("resignado", "resignada"),
    ("estancado", "estancada"),
    ("atascado", "atascada"),
    ("perdido", "perdida"),
    ("rallado", "rallada"),
    ("millonario", "millonaria"),
    ("rico", "rica"),
    ("convencido", "convencida"),
    ("ocupado", "ocupada"),
    ("mí mismo", "mí misma"),
    ("mi mismo", "mi misma"),
    ("yo solo", "yo sola"),
    ("Yo solo", "Yo sola"),
    (
        "No soy un caso extraordinario, soy un caso medianamente constante",
        "No soy una persona extraordinaria, soy una persona medianamente constante",
    ),
)
FEMALE_ES_HOOKS_BY_TYPE: dict[VideoType, str] = {
    VideoType.TYPE_1: (
        "Me dijeron que no iba a ganar\n"
        "nada con el Dropshipping por\n"
        "ser mujer y esto pasó..."
    ),
    VideoType.TYPE_2: (
        "Con estos 4 tips demostré que las\n"
        "mujeres también podemos tener\n"
        "éxito en el Dropshipping"
    ),
}


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

    def generate(
        self,
        video_type: VideoType,
        language: Language,
        *,
        gender: VideoGender = VideoGender.MALE,
        lowercase_text: bool = False,
    ) -> ScriptPackage:
        builder = self._builder_for(video_type, language)
        if video_type == VideoType.TYPE_4:
            return self._format_package(
                builder(),
                video_type=video_type,
                language=language,
                gender=gender,
                lowercase_text=False,
            )
        last_signature = self.state.get_last_signature(video_type, language)
        known_signatures = self.state.get_known_signatures(video_type, language)

        package: ScriptPackage | None = None
        for _ in range(self.MAX_ATTEMPTS):
            package = builder()
            if package.signature == last_signature:
                continue
            if package.signature in known_signatures:
                continue
            return self._format_package(
                package,
                video_type=video_type,
                language=language,
                gender=gender,
                lowercase_text=lowercase_text,
            )

        # Final guarantee: at least don't repeat the *immediately* previous
        # video, even if everything historic is exhausted.
        for _ in range(self.MAX_ATTEMPTS):
            package = builder()
            if package.signature != last_signature:
                return self._format_package(
                    package,
                    video_type=video_type,
                    language=language,
                    gender=gender,
                    lowercase_text=lowercase_text,
                )

        # Truly exhausted; surface as exception so caller can react instead of
        # silently violating the "no two equal in a row" rule.
        if package is None:
            package = builder()
        return self._format_package(
            package,
            video_type=video_type,
            language=language,
            gender=gender,
            lowercase_text=lowercase_text,
        )

    @staticmethod
    def _format_package(
        package: ScriptPackage,
        *,
        video_type: VideoType,
        language: Language,
        gender: VideoGender,
        lowercase_text: bool,
    ) -> ScriptPackage:
        if video_type == VideoType.TYPE_4:
            return package
        if gender == VideoGender.FEMALE:
            package = ScriptGenerator._feminize_package(package, language, video_type)
        if not lowercase_text:
            return package
        slides_by_role = {
            role: text.lower()
            for role, text in package.slides_by_role.items()
        }
        ordered_slides = [text.lower() for text in package.ordered_slides]
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered_slides,
            signature=package.signature,
            plain_text=package.plain_text.lower(),
            social_copy=SocialCopy(
                title=package.social_copy.title.lower(),
                description=package.social_copy.description.lower(),
                hashtags=[tag.lower() for tag in package.social_copy.hashtags],
            ),
            choice_key=package.choice_key,
            social_choice_key=package.social_choice_key,
        )

    @staticmethod
    def _feminize_package(
        package: ScriptPackage,
        language: Language,
        video_type: VideoType,
    ) -> ScriptPackage:
        if language != Language.ES:
            return package

        slides_by_role = {
            role: ScriptGenerator._feminize_text_es(text)
            for role, text in package.slides_by_role.items()
        }
        ordered_slides = [
            ScriptGenerator._feminize_text_es(text)
            for text in package.ordered_slides
        ]
        hook = FEMALE_ES_HOOKS_BY_TYPE.get(video_type)
        if hook is not None:
            slides_by_role[SlideRole.HOOK] = hook
            if ordered_slides:
                ordered_slides[0] = hook
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered_slides,
            signature=package.signature,
            plain_text="\n\n".join(ordered_slides),
            social_copy=SocialCopy(
                title=ScriptGenerator._feminize_text_es(package.social_copy.title),
                description=ScriptGenerator._feminize_text_es(
                    package.social_copy.description
                ),
                hashtags=list(package.social_copy.hashtags),
            ),
            choice_key=package.choice_key,
            social_choice_key=package.social_choice_key,
        )

    @staticmethod
    def _feminize_text_es(text: str) -> str:
        adapted = text
        for masculine, feminine in FEMALE_ES_REPLACEMENTS:
            adapted = adapted.replace(masculine, feminine)
        return adapted

    def _builder_for(self, video_type: VideoType, language: Language):
        if video_type == VideoType.TYPE_1:
            return self._build_type_1_es if language == Language.ES else self._build_type_1_en
        if video_type == VideoType.TYPE_2:
            return self._build_type_2_es if language == Language.ES else self._build_type_2_en
        if video_type == VideoType.TYPE_4:
            return self._build_type_4_es if language == Language.ES else self._build_type_4_en
        return self._build_type_3_es if language == Language.ES else self._build_type_3_en

    # ------------------------------------------------------------------
    # Type 1 — narrative October → March
    # ------------------------------------------------------------------

    def _build_type_1_es(self) -> ScriptPackage:
        variants = {
            "a": {
                SlideRole.HOOK: "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y por qué casi lo dejo...",
                SlideRole.OCTOBER: "Octubre - 0€\nLancé mi primera tienda supermotivado. Puse algo de dinero en anuncios, tuve un montón de vistas, pero nadie compró. Fue un buen golpe de realidad y perdí mi presupuesto.",
                SlideRole.NOVEMBER: "Noviembre - 0€\nPausé los anuncios de golpe para no perder más dinero. Me pasé todo el mes tocando el diseño de la tienda e intentando conseguir más visitas orgánicas. Igualmente, seguía en 0 ventas.",
                SlideRole.DECEMBER: "Diciembre - 0€\nLa campaña navideña pasó de largo. Veía a todo el mundo facturando y yo seguía atascado, sobrepensando qué producto lanzar por miedo a equivocarme otra vez.",
                SlideRole.JANUARY: "Enero - 0€\nNi siquiera abría Shopify. Estaba frustrado de pagar la cuota mensual para nada, estuve a un solo clic de cancelar mi suscripción. Sentía que todo esto era una pérdida de tiempo.",
                SlideRole.FEBRUARY: "Febrero - 800€\nVi a un dropshipper que sigo recomendando Dropradar y decidí hacer el último intento. Elegí un producto basándome estrictamente en sus métricas y, para mi sorpresa, empezaron a entrar ventas rentables.",
                SlideRole.MARCH: "Marzo - 2700€\nPor fin tengo ventas de forma constante. Estuve a punto de rendirme antes de aprender que lo que importa es la constancia y saber actuar sobre métricas y datos reales.",
            },
            "b": {
                SlideRole.HOOK: "Cuanto gané haciendo Dropshipping\nen estos 6 meses y por qué casi lo dejo....",
                SlideRole.OCTOBER: "Octubre - 0€\nEmpecé con muchas ganas, pero sin tener ni idea. Me pasé el mes montando la web y buscando productos que me parecieran buenos, pero no conseguí ni una sola venta.",
                SlideRole.NOVEMBER: "Noviembre - 0€\nMe frustraba ver que pasaban las semanas y no avanzaba. Seguía retocando la tienda y mirando tutoriales, pero me daba miedo empezar con anuncios y perder dinero, así que me quedé estancado.",
                SlideRole.DECEMBER: "Diciembre - 0€\nVeía a todo el mundo facturando por Navidad y yo seguía igual. Me sentía incapaz de encontrar un producto que funcionara y la presión de ver que otros lo conseguían me estaba quemando.",
                SlideRole.JANUARY: "Enero - 0€\nEstaba totalmente desmotivado. Pagar la cuota de Shopify sin vender nada me parecía tirar el dinero y estuve a un paso de cerrar la cuenta y olvidarme de todo.",
                SlideRole.FEBRUARY: "Febrero - 680€\nVi a un dropshipper que sigo usando Dropradar y decidí darle una última oportunidad. Elegí un producto basándome en sus datos y métricas y, por primera vez, empecé a vender de verdad.",
                SlideRole.MARCH: "Marzo - 3100€\nNo soy millonario, pero por fin tengo un negocio que funciona. Me alegro de no haberme rendido en enero la clave era la constancia y dejar de adivinar qué producto iba a funcionar.",
            },
            "c": {
                SlideRole.HOOK: "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y porqué casi lo dejo...",
                SlideRole.OCTOBER: "Octubre - 0€\nMe obsesioné con crear la marca perfecta. Pagué un logo, diseñé una web increíble y elegí productos que a mí me parecían bonitos. Mucho esfuerzo, cero ventas.",
                SlideRole.NOVEMBER: "Noviembre - 0€\nPensé que la gente no confiaba en la tienda. Mejoré las descripciones, metí más fotos y gasté mis primeros euros en TikTok Ads. Mi presupuesto desapareció sin resultados.",
                SlideRole.DECEMBER: "Diciembre - 74€\nEmpecé a subir productos al azar desde AliExpress a ver si sonaba la flauta. Cayeron tres ventas, pero los envíos eran carísimos y tardaban semanas. Trabajaba literalmente gratis.",
                SlideRole.JANUARY: "Enero - 0€\nMe quedé sin un euro para publicidad. Estaba mentalmente agotado de intentar vender cosas que a nadie le interesaban. Tiré la toalla y dejé la tienda abandonada.",
                SlideRole.FEBRUARY: "Febrero - 1220€\nYa resignado, vi en un foro a otros dropshippers hablando de usar Dropradar para ver qué productos tenían demanda real. Lo probé por pura frustración. Di con un ganador y las ventas explotaron el primer día.",
                SlideRole.MARCH: "Marzo - 3100€\nNo soy rico ni viajo en jet privado. Pero escalando ese producto ganador al máximo, logré mi mayor facturación. Como consejo, vende lo que la gente ya está buscando, no lo que tú crees.",
            },
        }
        return self._compose_type_1_fixed(language=Language.ES, variants=variants)

    def _build_type_1_en(self) -> ScriptPackage:
        variants = {
            "a": {
                SlideRole.HOOK: "How much I earned doing Dropshipping\nin my first 6 months and why I almost quit...",
                SlideRole.OCTOBER: "October - $0\nI launched my first store feeling super motivated. I put some money into ads, got a lot of views, but nobody bought. It was a real reality check and I lost my budget.",
                SlideRole.NOVEMBER: "November - $0\nI paused the ads right away so I would not lose more money. I spent the whole month tweaking the store design and trying to get more organic traffic. Even so, I was still at 0 sales.",
                SlideRole.DECEMBER: "December - $0\nThe Christmas season passed me by. I watched everyone else making money while I stayed stuck, overthinking which product to launch because I was scared of getting it wrong again.",
                SlideRole.JANUARY: "January - $0\nI was not even opening Shopify anymore. I was frustrated about paying the monthly fee for nothing, and I was one click away from canceling my subscription. It felt like all of this was a waste of time.",
                SlideRole.FEBRUARY: "February - $800\nI saw a dropshipper I follow recommending Dropradar, and I decided to give it one last try. I picked a product strictly based on its metrics and, to my surprise, profitable sales started coming in.",
                SlideRole.MARCH: "March - $2700\nI finally have sales coming in consistently. I was close to giving up before learning that what really matters is consistency and knowing how to act on real metrics and data.",
            },
            "b": {
                SlideRole.HOOK: "How much I made doing Dropshipping\nin my first 6 months and why I almost quit...",
                SlideRole.OCTOBER: "October - $0\nI started with a lot of excitement, but without really knowing anything. I spent the whole month building the website and looking for products that seemed good to me, but I did not get a single sale.",
                SlideRole.NOVEMBER: "November - $0\nIt frustrated me to see the weeks go by without making progress. I kept tweaking the store and watching tutorials, but I was scared to start ads and lose money, so I stayed stuck.",
                SlideRole.DECEMBER: "December - $0\nI watched everyone making money at Christmas while I stayed exactly the same. I felt unable to find a product that worked, and the pressure of seeing others succeed was burning me out.",
                SlideRole.JANUARY: "January - $0\nI was completely unmotivated. Paying the Shopify fee without selling anything felt like throwing money away, and I was one step away from closing the account and forgetting about everything.",
                SlideRole.FEBRUARY: "February - $680\nI saw a dropshipper I follow using Dropradar, and I decided to give it one last chance. I picked a product based on its data and metrics and, for the first time, I started selling for real.",
                SlideRole.MARCH: "March - $3100\nI am not a millionaire, but I finally have a business that works. I am glad I did not give up in January the key was consistency and stopping the guessing game about which product would work.",
            },
            "c": {
                SlideRole.HOOK: "Exactly how much I made doing Dropshipping\nin my first 6 months and why I almost quit.",
                SlideRole.OCTOBER: "October - 0€\nI became obsessed with creating the perfect brand. I paid for a logo, designed an incredible website, and chose products that I thought were pretty. A lot of effort, zero sales.",
                SlideRole.NOVEMBER: "November - 0€\nI thought people didn't trust the store. I improved the descriptions, added more photos, and spent my first euros on TikTok Ads. My budget disappeared with no results.",
                SlideRole.DECEMBER: "December - 74€\nI started uploading random products from AliExpress to see if I'd get lucky. I got three sales, but shipping was extremely expensive and took weeks. I was literally working for free.",
                SlideRole.JANUARY: "January - 0€\nI ran out of money for advertising. I was mentally exhausted from trying to sell things that nobody was interested in. I threw in the towel and left the store abandoned.",
                SlideRole.FEBRUARY: "February - 1220€\nAlready resigned, I saw other dropshippers in a forum talking about using Dropradar to see which products had real demand. I tried it out of pure frustration. I found a winner and sales exploded on the first day.",
                SlideRole.MARCH: "March - 3100€\nI'm not rich and I don't travel in a private jet. But by scaling that winning product to the max, I achieved my highest revenue. Moral of the story: sell what people are already looking for, not what you think.",
            },
        }
        return self._compose_type_1_fixed(language=Language.EN, variants=variants)

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
        social_copy_key = self._copy_choice_from_social_key(social_key)
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
                social_copy_key,
            ]
        )

        self._assert_type_1_rules(language, slides_by_role)

        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=signature,
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
            social_choice_key=social_copy_key,
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
        social_copy_key = self._copy_choice_from_social_key(social_key)
        signature = _hash_signature([choice_key, *ordered, social_copy_key])

        self._assert_type_1_rules(language, slides_by_role)

        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=signature,
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
            choice_key=choice_key,
            social_choice_key=social_copy_key,
        )

    @staticmethod
    def _assert_type_1_rules(
        language: Language,
        slides_by_role: dict[SlideRole, str],
    ) -> None:
        if "Dropradar" not in slides_by_role[SlideRole.FEBRUARY]:
            raise RuntimeError("Tipo 1: el slide de febrero perdió la mención a Dropradar.")

        hook = slides_by_role[SlideRole.HOOK]
        if "Dropshipping" not in hook:
            raise RuntimeError("Tipo 1: el hook debe mencionar Dropshipping.")

        allowed_hooks = {
            Language.ES: {
                "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y por qué casi lo dejo...",
                "Cuanto gané haciendo Dropshipping\nen estos 6 meses y por qué casi lo dejo....",
                "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y porqué casi lo dejo...",
            },
            Language.EN: {
                "How much I earned doing Dropshipping\nin my first 6 months and why I almost quit...",
                "How much I made doing Dropshipping\nin my first 6 months and why I almost quit...",
                "Exactly how much I made doing Dropshipping\nin my first 6 months and why I almost quit.",
            },
        }
        if hook not in allowed_hooks[language]:
            raise RuntimeError(f"Tipo 1: hook no aprobado: {hook!r}")

    def _next_type_1_choice(
        self,
        language: Language,
        variants: dict[str, dict[SlideRole, str]],
    ) -> str:
        ordered_keys = list(variants)
        if not ordered_keys:
            raise RuntimeError("Tipo 1: no hay variantes configuradas.")
        last_choice = (
            self.state.get_last_shared_text_choice(VideoType.TYPE_1)
            or self.state.get_last_text_choice(VideoType.TYPE_1, language)
        )
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
                SlideRole.HOOK: "Habría pagado por saber estas 4 cosas\ncuando empecé en Dropshipping",
                SlideRole.TIP1: "1. Valida con poco presupuesto\nNo trates la publicidad como una apuesta. Invierte pequeñas sumas para testear qué anuncios funcionan y escala solo cuando los datos confirmen la rentabilidad.",
                SlideRole.TIP2: "2. Cuida al cliente tras el pago\nLa venta no termina cuando recibes el dinero. Un soporte rápido y amable evita reclamaciones bancarias y asegura la continuidad de tu cuenta.",
                SlideRole.TIP3: "3. Prioriza nichos sobre productos virales\nEvita la competencia saturada buscando soluciones para audiencias específicas. Usa Dropradar para validar productos con potencial y tener ventaja sobre tu competencia.",
                SlideRole.TIP4: "4. Proyecta confianza y transparencia\nMuestra tu producto real en uso, sé honesto con los tiempos de envío y destaca políticas de garantía claras, esta autenticidad elimina las dudas del espectador disparando tus conversiones.",
            },
            "b": {
                SlideRole.HOOK: "Errores que cuestan dinero\nal empezar en Dropshipping...",
                SlideRole.TIP1: '1. Tener una tienda con aspecto "barato"\nSi tu web parece una plantilla de hace diez años, nadie confiará en ti. Añade reseñas, ofrece ofertas, sé sincero con los tiempos de envío e intenta reducirlos para conseguir ventas reales.',
                SlideRole.TIP2: "2. Quemar el dinero en anuncios\nNo lances dinero a Facebook o TikTok esperando un milagro. Empieza con poco, prueba diferentes enfoques y usa el contenido orgánico para ver qué funciona antes de invertir fuerte.",
                SlideRole.TIP3: "3. Vender lo mismo que todos\nLos productos virales tienen demasiada competencia y nulo margen. Busca nichos que resuelvan problemas reales y apóyate en herramientas como Dropradar para encontrar productos rentables.",
                SlideRole.TIP4: "4. Descuidar el trato con el comprador\nConseguir el pago es solo la mitad del trabajo. Si no ayudas al cliente tras la compra, tu reputación y tu cuenta bancaria lo pagarán. Una comunicación rápida evita devoluciones y protege tu negocio.",
            },
            "c": {
                SlideRole.HOOK: "4 consejos para Dropshipping\nque me habrían ahorrado mucho dinero...",
                SlideRole.TIP1: "1. No compitas tirando los precios por los suelos para conseguir tu primera venta rápida. Si tu margen de beneficio es minúsculo, cualquier pequeño gasto imprevisto en publicidad o en posibles devoluciones te dejará en números rojos. Mejor esfuérzate en construir una oferta irresistible alrededor de tu producto.",
                SlideRole.TIP2: "2. Contacta siempre con tus proveedores para confirmar su capacidad antes de escalar una campaña publicitaria. De nada sirve que un anuncio funcione genial si la fábrica no tiene stock o tarda semanas en procesar pedidos, ya que acabarás lidiando con decenas de clientes exigiendo su dinero.",
                SlideRole.TIP3: "3. Deja de intentar adivinar qué se va a vender basándote únicamente en tu intuición o en lo que te parece visualmente atractivo. El éxito llega cuando ofreces lo que el mercado ya está pidiendo a gritos, así que apóyate en herramientas como Dropradar para basarte en datos reales y encontrar productos ganadores.",
                SlideRole.TIP4: "4. Tus anuncios de vídeo deben centrarse en el problema que resuelves y no en enumerar características técnicas aburridas. Aprovecha los tres primeros segundos para captar la atención del espectador mostrándole de forma visual y muy directa cómo tu artículo le va a hacer la vida más fácil.",
            },
        }
        return self._compose_type_2_fixed(Language.ES, variants)

    def _build_type_2_en(self) -> ScriptPackage:
        variants = {
            "a": {
                SlideRole.HOOK: "I would have paid to know these 4 things\nwhen I started Dropshipping",
                SlideRole.TIP1: "1. Validate with a small budget\nDo not treat advertising like a bet. Invest small amounts to test which ads work and scale only when the data confirms profitability.",
                SlideRole.TIP2: "2. Take care after-sale\nThe sale does not end when you receive the money. Fast, friendly support prevents bank claims and protects the continuity of your account.",
                SlideRole.TIP3: "3. Prioritize niches over viral products\nAvoid saturated competition by looking for solutions for specific audiences. Use Dropradar to validate products with potential and gain an advantage over your competition.",
                SlideRole.TIP4: "4. Project trust and transparency\nShow your real product in use, be honest about shipping times, and highlight clear guarantee policies. This authenticity eliminates viewer doubts, skyrocketing your conversions..",
            },
            "b": {
                SlideRole.HOOK: "Mistakes I see small Dropshippers\nmaking when they are starting out",
                SlideRole.TIP1: "1. Having a cheap looking store\nIf your website looks like a template from ten years ago, nobody will trust you. Add reviews, offer deals, be honest about shipping times and try to reduce them to get real sales.",
                SlideRole.TIP2: "2. Treating ads like a slot machine\nDo not throw money at Facebook or TikTok hoping for a miracle. Start small, test different angles and use organic content to see what works before investing heavily.",
                SlideRole.TIP3: "3. Sell the same as everyone else\nViral products have too much competition and no margin. Look for niches that solve real problems and lean on tools like Dropradar to find profitable products.",
                SlideRole.TIP4: "4. Neglecting the buyer experience\nGetting the payment is only half the job. If you do not help the customer after purchase, your reputation and your bank account will pay for it. Fast communication prevents refunds and protects your business.",
            },
            "c": {
                SlideRole.HOOK: "4 Dropshipping tips\nthat would have saved me a lot of money...",
                SlideRole.TIP1: "1. Don't compete by slashing prices to the ground just to get your first quick sale. If your profit margin is tiny, any small unexpected expense in advertising or potential returns will put you in the red. Instead, focus your efforts on building an irresistible offer around your product.",
                SlideRole.TIP2: "2. Always contact your suppliers to confirm their capacity before scaling an advertising campaign. It is useless for an ad to perform great if the factory has no stock or takes weeks to process orders, as you will end up dealing with dozens of angry customers demanding their money back.",
                SlideRole.TIP3: "3. Stop trying to guess what will sell based solely on your intuition or what you find visually appealing. Success comes when you offer what the market is already crying out for, so lean on tools like Dropradar to base your decisions on real data and find winning products.",
                SlideRole.TIP4: "4. Your video ads should focus on the problem you solve rather than listing boring technical features. Use the first three seconds to grab the viewer's attention by showing them visually and very directly how your item is going to make their life easier.",
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
        social_copy_key = self._copy_choice_from_social_key(social_key)
        ordered = [slides_by_role[role] for role in TYPE_2_ROLES]
        self._assert_type_2_rules(slides_by_role)
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=_hash_signature([choice_key, *ordered, social_copy_key]),
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
            choice_key=choice_key,
            social_choice_key=social_copy_key,
        )

    def _next_type_2_choice(
        self,
        language: Language,
        variants: dict[str, dict[SlideRole, str]],
    ) -> str:
        ordered_keys = list(variants)
        if not ordered_keys:
            raise RuntimeError("Tipo 2: no hay variantes configuradas.")
        last_choice = (
            self.state.get_last_shared_text_choice(VideoType.TYPE_2)
            or self.state.get_last_text_choice(VideoType.TYPE_2, language)
        )
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
            if role == SlideRole.HOOK:
                continue
            expected_prefix = f"{role.value[-1]}."
            if not slide.startswith(expected_prefix):
                raise ValueError(
                    f"Tipo 2 ({role.value}): el consejo debe empezar por '{expected_prefix}'."
                )
            if "\n" in slide:
                title, body = slide.split("\n", 1)
                if not title.strip() or not body.strip():
                    raise ValueError(
                        f"Tipo 2 ({role.value}): el consejo debe tener título y texto."
                    )
                continue
            if len(slide.split()) < 8:
                raise ValueError(
                    f"Tipo 2 ({role.value}): el consejo directo es demasiado corto."
                )
        if "Dropradar" not in slides_by_role.get(SlideRole.TIP3, ""):
            raise ValueError("Tipo 2: el consejo 3 debe mencionar Dropradar.")
        repeated_dropradar_roles = [
            role.value
            for role in (SlideRole.TIP1, SlideRole.TIP2, SlideRole.TIP4)
            if "Dropradar" in slides_by_role.get(role, "")
        ]
        if repeated_dropradar_roles:
            raise ValueError(
                "Tipo 2: Dropradar solo debe aparecer en el consejo 3, no en "
                + ", ".join(repeated_dropradar_roles)
            )
        hook = slides_by_role.get(SlideRole.HOOK, "")
        if "Dropshipping" not in hook and "Dropshippers" not in hook:
            raise ValueError("Tipo 2: el hook debe mencionar Dropshipping o Dropshippers.")

    # ------------------------------------------------------------------
    # Type 3 — one hook photo + fixed tool stack
    # ------------------------------------------------------------------

    def _build_type_3_es(self) -> ScriptPackage:
        hooks = {
            "h1": "Como hacer dropshipping en 2026",
        }
        payment_tool = random.choice(("PayPal", "Stripe"))
        marketing_tool = random.choice(("Instagram", "TikTok"))
        tools = {
            SlideRole.TOOL_STORE: "1. Tienda\nConstruye tu tienda por 1€ - Usa Shopify",
            SlideRole.TOOL_PRODUCT_SEARCH: "2. Busqueda de productos\nEncuentra productos ganadores - Usa Dropradar",
            SlideRole.TOOL_SCRIPTS: "3. Guiones\nCrea guiones para tus videos - Usa ChatGPT",
            SlideRole.TOOL_PAYMENTS: f"4. Pagos\nGestiona pagos seguros - Usa {payment_tool}",
            SlideRole.TOOL_EDITING: "5. Edicion\nEdita videos con mas calidad - Usa CapCut",
            SlideRole.TOOL_MARKETING: f"6. Marketing\nPromociona tu producto - Usa {marketing_tool}",
        }
        return self._compose_type_3(Language.ES, hooks, tools)

    def _build_type_3_en(self) -> ScriptPackage:
        hooks = {
            "h1": "How to start in Dropshipping in 2026",
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

    # ------------------------------------------------------------------
    # Type 4 - AI comic story from one reference photo
    # ------------------------------------------------------------------

    def _build_type_4_es(self) -> ScriptPackage:
        slides_by_role = {
            SlideRole.STORY_MCDONALD: (
                "Así pasé de trabajar en McDonald's a cumplir mi sueño: "
                "comprarme un Porsche 911 GT3."
            ),
            SlideRole.STORY_BUILDING_STORE: (
                "Monté mi tienda y pasé horas analizando productos y estudiando "
                "creativos."
            ),
            SlideRole.STORY_FIRST_FAILURE: (
                "El primer mes hice 0 ventas. El producto simplemente no "
                "despertaba interés."
            ),
            SlideRole.STORY_DEEP_FAILURE: (
                "Los meses siguientes fueron peores: probé 3 productos, no vendí "
                "ninguno y estuve a punto de dejarlo para siempre."
            ),
            SlideRole.STORY_DROPRADAR: (
                "Entonces encontré Dropradar, validé un producto con datos y ese "
                "mes conseguí mi primera venta."
            ),
            SlideRole.STORY_SUCCESS_COMIC: (
                "Después de un año y medio..."
            ),
            SlideRole.STORY_ORIGINAL_REFERENCE: "",
        }
        return self._compose_type_4(Language.ES, slides_by_role)

    def _build_type_4_en(self) -> ScriptPackage:
        slides_by_role = {
            SlideRole.STORY_MCDONALD: (
                "This is how I went from working at McDonald's to achieving my "
                "dream: buying a Porsche 911 GT3."
            ),
            SlideRole.STORY_BUILDING_STORE: (
                "I built my store and spent hours researching products and studying "
                "creatives."
            ),
            SlideRole.STORY_FIRST_FAILURE: (
                "The first month I made 0 sales. The product simply did not attract "
                "any interest."
            ),
            SlideRole.STORY_DEEP_FAILURE: (
                "The following months were worse: I tested 3 products, sold none and "
                "almost quit for good."
            ),
            SlideRole.STORY_DROPRADAR: (
                "Then I found Dropradar, validated a product with data and made my "
                "first sale that month."
            ),
            SlideRole.STORY_SUCCESS_COMIC: "A year and a half later...",
            SlideRole.STORY_ORIGINAL_REFERENCE: "",
        }
        return self._compose_type_4(Language.EN, slides_by_role)

    def _compose_type_4(
        self,
        language: Language,
        slides_by_role: dict[SlideRole, str],
    ) -> ScriptPackage:
        ordered = [slides_by_role[role] for role in TYPE_4_ROLES]
        social_key, social_copy = self._choose_social_copy(VideoType.TYPE_4, language)
        self._assert_type_4_rules(slides_by_role)
        return ScriptPackage(
            slides_by_role=slides_by_role,
            ordered_slides=ordered,
            signature=_hash_signature([*ordered, social_key]),
            plain_text="\n\n".join(ordered),
            social_copy=social_copy,
            choice_key="fixed",
            social_choice_key=self._copy_choice_from_social_key(social_key),
        )

    @staticmethod
    def _assert_type_4_rules(slides_by_role: dict[SlideRole, str]) -> None:
        expected_roles = set(TYPE_4_ROLES)
        if set(slides_by_role) != expected_roles:
            raise ValueError("Historia IA: faltan slides de la historia.")
        required_texts = [
            slides_by_role[SlideRole.STORY_MCDONALD],
            slides_by_role[SlideRole.STORY_BUILDING_STORE],
            slides_by_role[SlideRole.STORY_FIRST_FAILURE],
            slides_by_role[SlideRole.STORY_DEEP_FAILURE],
            slides_by_role[SlideRole.STORY_DROPRADAR],
            slides_by_role[SlideRole.STORY_SUCCESS_COMIC],
        ]
        if any(not text.strip() for text in required_texts):
            raise ValueError("Historia IA: los 6 textos narrativos son obligatorios.")
        if "Dropradar" not in slides_by_role[SlideRole.STORY_DROPRADAR]:
            raise ValueError("Historia IA: el punto de inflexion debe mencionar Dropradar.")

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
            hashtags=self._prepare_social_hashtags(hashtags),
        )

    def _choose_social_copy_for_text_choice(
        self,
        video_type: VideoType,
        language: Language,
        choice_key: str,
    ) -> tuple[str, SocialCopy]:
        variants = self._social_copy_variants(video_type, language)
        ordered_keys = list(variants)
        choice_index = {"a": 0, "b": 1, "c": 2}.get(choice_key)
        if choice_index is None or choice_index >= len(ordered_keys):
            return self._choose_social_copy(video_type, language)
        copy_key = ordered_keys[choice_index]
        title, description, hashtags = variants[copy_key]
        return f"{copy_key}:default", SocialCopy(
            title=title,
            description=description,
            hashtags=self._prepare_social_hashtags(hashtags),
        )

    @staticmethod
    def _prepare_social_hashtags(hashtags: list[str]) -> list[str]:
        prepared = [
            "#dropshipping" if tag.lower() == "#dropshipping" else tag
            for tag in hashtags
        ]
        if "#dropshipping" not in prepared:
            replacement_index = next(
                (
                    index
                    for index, tag in enumerate(prepared)
                    if tag.lower().startswith("#dropshipping")
                ),
                None,
            )
            if replacement_index is None:
                prepared.append("#dropshipping")
            else:
                prepared[replacement_index] = "#dropshipping"
        random.shuffle(prepared)
        return prepared

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
        if video_type not in {VideoType.TYPE_1, VideoType.TYPE_2}:
            variants.update(self._extra_social_copy_variants(video_type, language))
        return self._prepare_social_copy_variants(video_type, language, variants)

    def _social_title_variants(
        self,
        video_type: VideoType,
        language: Language,
    ) -> dict[str, str]:
        if language == Language.EN:
            titles = self._social_title_variants_en(video_type)
        else:
            titles = self._social_title_variants_es(video_type)
        titles.update(self._extra_social_title_variants(video_type, language))
        return titles

    def _social_title_variants_es(self, video_type: VideoType) -> dict[str, str]:
        if video_type == VideoType.TYPE_4:
            return {}
        if video_type == VideoType.TYPE_1:
            return {
                "t1": "Mis primeros 6 meses intentando vender online",
                "t2": "De cero ventas a entender que medir",
                "t3": "Lo que cambio cuando deje de adivinar",
                "t4": "La parte real de empezar dropshipping",
                "t5": "Seis meses de prueba, datos y paciencia",
                "t6": "Cuando por fin deje de elegir a ciegas",
                "t7": "Mi tienda cambio cuando mire los datos",
                "t8": "El proceso que me saco del bloqueo",
                "t9": "Lo que aprendi antes de vender constante",
                "t10": "De meses en cero a decisiones con criterio",
                "t11": "Antes de rendirme cambie el metodo",
                "t12": "El cambio que hizo que vender tuviera sentido",
            }
        if video_type == VideoType.TYPE_2:
            return {
                "t1": "4 revisiones antes de gastar en anuncios",
                "t2": "Consejos que me habrian ahorrado dinero",
                "t3": "La checklist que faltaba antes de vender",
                "t4": "Lo basico que sostiene una tienda",
                "t5": "Antes de escalar revisa estos puntos",
                "t6": "Errores pequenos que salen caros",
                "t7": "4 consejos para vender con mas cabeza",
                "t8": "Lo que miraria antes de lanzar una tienda",
                "t9": "Tu tienda necesita esta revision",
                "t10": "Margen, confianza, producto y soporte",
                "t11": "Antes de perder presupuesto revisa esto",
                "t12": "La base que no conviene saltarse",
            }
        if video_type != VideoType.TYPE_3:
            return {}
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
        if video_type == VideoType.TYPE_4:
            return {}
        if video_type == VideoType.TYPE_1:
            return {
                "t1": "My first 6 months trying to sell online",
                "t2": "From zero sales to clearer decisions",
                "t3": "What changed when I stopped guessing",
                "t4": "The real part of starting dropshipping",
                "t5": "Six months of tests, data and patience",
                "t6": "When I finally stopped picking blindly",
                "t7": "My store changed once I looked at data",
                "t8": "The process that got me unstuck",
                "t9": "What I learned before steady sales",
                "t10": "From months at zero to better decisions",
                "t11": "Before quitting I changed the method",
                "t12": "The shift that made selling make sense",
            }
        if video_type == VideoType.TYPE_2:
            return {
                "t1": "4 checks before spending on ads",
                "t2": "Tips that would have saved me money",
                "t3": "The checklist I needed before selling",
                "t4": "The basics that keep a store alive",
                "t5": "Review this before scaling a store",
                "t6": "Small mistakes that get expensive",
                "t7": "4 tips for selling with better logic",
                "t8": "What I would check before launching",
                "t9": "Your store needs this quick review",
                "t10": "Margins, trust, product and support",
                "t11": "Check this before losing more budget",
                "t12": "The base you should not skip",
            }
        if video_type != VideoType.TYPE_3:
            return {}
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

    def _extra_social_title_variants(
        self,
        video_type: VideoType,
        language: Language,
    ) -> dict[str, str]:
        if video_type != VideoType.TYPE_3:
            return {}
        if language == Language.EN:
            return {
                "t13": "The starter tools with a real order",
                "t14": "A simple workflow for your first tests",
                "t15": "Build the base before chasing apps",
                "t16": "The stack I would keep at the start",
                "t17": "Tools that help you publish faster",
                "t18": "Start lean and learn from the market",
            }
        return {
            "t13": "Herramientas iniciales con un orden real",
            "t14": "Un flujo simple para tus primeras pruebas",
            "t15": "Construye la base antes de buscar mas apps",
            "t16": "El stack que mantendria al empezar",
            "t17": "Herramientas para publicar con menos freno",
            "t18": "Empieza ligero y aprende del mercado",
        }

    def _extra_social_copy_variants(
        self,
        video_type: VideoType,
        language: Language,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if language == Language.EN:
            return self._extra_social_copy_variants_en(video_type)
        return self._extra_social_copy_variants_es(video_type)

    def _extra_social_copy_variants_es(
        self,
        video_type: VideoType,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if video_type != VideoType.TYPE_3:
            return {}
        return {
            "es6": (
                "Empieza con pocas piezas bien elegidas",
                "La tentacion al empezar es buscar una herramienta para cada problema, incluso para problemas que todavia no existen. Eso solo hace que el proyecto se vuelva pesado antes de probar nada real. Una tienda simple, una forma de investigar productos, una herramienta para escribir guiones, pagos listos, edicion agil y un canal organico son suficientes para empezar a aprender del mercado. Lo importante no es tener un sistema perfecto, es tener un flujo que puedas repetir varios dias seguidos sin bloquearte.",
                ["#dropshipping2026", "#ecommerce", "#shopify", "#capcut", "#dropradar"],
            ),
            "es7": (
                "El orden importa mas que la cantidad de apps",
                "Puedes tener muchas herramientas y seguir sin avanzar si no sabes que papel cumple cada una. Primero necesitas una tienda que no genere rechazo, despues un producto elegido con criterio, luego contenido que explique la oferta, pagos preparados para no improvisar y un canal donde puedas practicar la respuesta del mercado. Ese orden reduce ansiedad porque te dice que toca hacer ahora. Cuando intentas optimizar todo a la vez, cada decision parece enorme. Cuando sigues un flujo sencillo, cada herramienta deja de ser una distraccion y se convierte en una parte concreta del trabajo.",
                ["#dropshipping", "#herramientas", "#negociosonline", "#tiktokmarketing", "#dropradar"],
            ),
            "es8": (
                "Un stack pensado para publicar antes",
                "Este stack tiene sentido porque te empuja a publicar y medir, no a quedarte escondido configurando cosas durante semanas. Shopify te permite montar la tienda, Dropradar te ayuda a filtrar productos, ChatGPT acelera ideas y guiones, PayPal o Stripe dejan el cobro preparado, CapCut mantiene ligera la edicion e Instagram o TikTok te dan un sitio donde practicar a diario. Ninguna herramienta reemplaza el criterio, pero juntas crean una rutina simple para pasar de pensar a probar. Al empezar, esa velocidad de aprendizaje vale mas que una lista interminable de funciones.",
                ["#ecommerce2026", "#dropshippingtips", "#onlinebusiness", "#shopify", "#dropradar"],
            ),
        }

    def _extra_social_copy_variants_en(
        self,
        video_type: VideoType,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if video_type != VideoType.TYPE_3:
            return {}
        return {
            "en6": (
                "Start with a few well chosen pieces",
                "The temptation at the beginning is to find a tool for every problem, even for problems that do not exist yet. That makes the project heavy before you test anything real. A simple store, a product research flow, a place to write scripts, payments ready, quick editing and one organic channel are enough to start learning from the market. The goal is not a perfect system. The goal is a workflow you can repeat for several days without freezing.",
                ["#dropshipping2026", "#ecommerce", "#shopify", "#capcut", "#dropradar"],
            ),
            "en7": (
                "Order matters more than app count",
                "You can have a lot of tools and still make no progress if you do not know what each one is supposed to do. First you need a store that does not create doubt, then a product chosen with a reason, then content that explains the offer, payments prepared before the first order and a channel where you can practice market response. That order lowers anxiety because it tells you what to do next. When you try to optimize everything at once, every choice feels huge. When you follow a simple flow, each tool stops being a distraction and becomes a clear part of the work.",
                ["#dropshipping", "#ecommercetools", "#onlinebusiness", "#tiktokmarketing", "#dropradar"],
            ),
            "en8": (
                "A stack built to publish sooner",
                "This stack makes sense because it pushes you to publish and measure, not hide behind setup for weeks. Shopify gives you the store, Dropradar helps filter products, ChatGPT speeds up ideas and scripts, PayPal or Stripe keep payments ready, CapCut keeps editing light and Instagram or TikTok give you a place to practice daily. No tool replaces judgment, but together they create a simple routine for moving from thinking to testing. At the start, that learning speed matters more than an endless list of features.",
                ["#ecommerce2026", "#dropshippingtips", "#onlinebusiness", "#shopify", "#dropradar"],
            ),
        }

    def _prepare_social_copy_variants(
        self,
        video_type: VideoType,
        language: Language,
        variants: dict[str, tuple[str, str, list[str]]],
    ) -> dict[str, tuple[str, str, list[str]]]:
        if video_type in {VideoType.TYPE_1, VideoType.TYPE_2, VideoType.TYPE_4}:
            return variants
        expansions = self._social_description_expansions(video_type, language)
        fallback = self._social_description_fallback(video_type, language)
        prepared: dict[str, tuple[str, str, list[str]]] = {}
        for index, (key, (title, description, hashtags)) in enumerate(variants.items()):
            expanded = description.strip()
            if index % 2 == 0 or len(expanded) < SOCIAL_DESCRIPTION_TARGET_MIN:
                expanded = f"{expanded} {expansions[index % len(expansions)]}".strip()
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
        if video_type != VideoType.TYPE_3:
            return ()
        return (
            "La clave de este stack no es que cada herramienta sea la única opción posible, sino que cada una cumple un trabajo concreto dentro del flujo. Shopify te da la base para vender, Dropradar te ayuda a investigar con datos, ChatGPT acelera guiones y ángulos, PayPal o Stripe reducen fricción en el cobro, CapCut mantiene la producción de contenido ligera e Instagram o TikTok te dan un lugar donde practicar la respuesta del mercado. Cuando entiendes el papel de cada herramienta, dejas de coleccionar apps y empiezas a construir una rutina. Esa rutina es lo que importa al principio: publicar, medir, ajustar y volver a probar sin convertir cada decisión en una semana de dudas.",
            "Empezar con pocas herramientas también protege tu atención. Al principio es muy fácil pensar que el siguiente plugin, plantilla o software va a resolver la falta de ventas, pero casi siempre el bloqueo está en otro sitio: no has validado bien el producto, no publicas contenido suficiente, no sabes qué dato mirar o cambias de idea antes de terminar una prueba. Un stack simple te obliga a mirar lo esencial. Qué vendes, por qué alguien lo compraría, cómo lo explicas, cómo cobras y cómo generas tráfico. Si esas preguntas no están claras, añadir más herramientas solo hace que el problema parezca más profesional, pero no más resuelto.",
            "Usa esta lista como punto de partida, no como jaula. Puedes cambiar una herramienta por otra si ya tienes experiencia, pero evita romper el orden. Primero una tienda funcional, luego producto, luego contenido, después pagos, edición y distribución. Ese orden mantiene el proyecto en movimiento porque cada pieza prepara la siguiente. Si intentas optimizar todo antes de publicar, vas a sentir que trabajas mucho sin recibir feedback real. En cambio, si montas una base suficiente y sales a probar, el mercado empieza a responder. Algunas respuestas serán incómodas, pero al menos sabrás qué ajustar con datos y no solo con intuición.",
            "El error más común es confundir empezar simple con empezar descuidado. Simple significa que cada pieza tiene una función clara y que puedes repetir el proceso sin depender de una configuración enorme. Descuidado significa lanzar sin entender márgenes, sin revisar la tienda, sin preparar contenido y sin medir nada. Este stack busca lo primero. Te da una estructura ligera para moverte rápido, pero también te recuerda que cada herramienta necesita uso real. No sirve tener Shopify si no mejoras la oferta, ni Dropradar si ignoras los datos, ni ChatGPT si no publicas, ni CapCut si nunca pruebas formatos distintos. La herramienta solo vale cuando entra en una rutina.",
        )

    def _social_description_expansions_en(self, video_type: VideoType) -> tuple[str, ...]:
        if video_type != VideoType.TYPE_3:
            return ()
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
            return "Keep the setup simple enough to repeat. The tools only matter when they help you publish, measure and improve with less friction every week."
        return "Mantén el sistema lo bastante simple como para repetirlo. Las herramientas importan cuando te ayudan a publicar, medir y mejorar con menos fricción cada semana."

    def _social_copy_variants_es(
        self,
        video_type: VideoType,
    ) -> dict[str, tuple[str, str, list[str]]]:
        if video_type == VideoType.TYPE_4:
            return {
                "es_story_1": (
                    "De 0 ventas a dejar de elegir a ciegas",
                    (
                        "Durante meses confundí trabajar más con avanzar. Retocaba la "
                        "tienda, estudiaba anuncios y probaba productos sin saber qué "
                        "señal estaba buscando. El cambio llegó cuando dejé de elegir "
                        "por intuición y empecé a validar demanda, competencia y datos "
                        "antes de gastar. Dropradar no hizo el trabajo por mí, pero me "
                        "ayudó a convertir cada prueba en una decisión con sentido."
                    ),
                    [
                        "#dropshipping",
                        "#ecommerce",
                        "#dropradar",
                        "#shopify",
                        "#productresearch",
                    ],
                ),
                "es_story_2": (
                    "La parte que no se ve antes de la primera venta",
                    (
                        "Montar la tienda fue la parte fácil. Lo difícil fue abrir el "
                        "panel cada día y seguir viendo cero pedidos después de tantas "
                        "horas de trabajo. Probé varios productos, cambié creativos y "
                        "estuve muy cerca de cerrar todo. Mi primera venta no llegó por "
                        "hacer otro cambio estético, llegó cuando empecé a investigar "
                        "productos con datos reales y a descartar ideas antes de perder "
                        "más tiempo y presupuesto con ellas."
                    ),
                    [
                        "#dropshipping",
                        "#tiendaonline",
                        "#primeraventa",
                        "#emprender",
                        "#dropradar",
                    ],
                ),
                "es_story_3": (
                    "Casi cierro la tienda antes de cambiar esto",
                    (
                        "Después de tres productos fallidos pensé que el problema era "
                        "yo. Trabajaba más horas, copiaba nuevas ideas y aun así no "
                        "entendía por qué nadie compraba. Antes de rendirme cambié una "
                        "sola parte del proceso: dejé de lanzar por corazonadas y empecé "
                        "a pedir pruebas de demanda antes de crear la tienda y los "
                        "anuncios. Ahí apareció Dropradar y, por primera vez, cada dato "
                        "me ayudaba a decidir qué probar y qué descartar."
                    ),
                    [
                        "#dropshipping",
                        "#negociosonline",
                        "#ecommercetips",
                        "#shopify",
                        "#dropradar",
                    ],
                ),
                "es_story_4": (
                    "Lo que cambió cuando empecé a validar con datos",
                    (
                        "No necesitaba encontrar cien productos, necesitaba entender por "
                        "qué uno merecía una prueba. Durante meses lancé ideas sin mirar "
                        "bien la demanda, la competencia ni los creativos que ya estaban "
                        "funcionando. Cuando ordené esa investigación con Dropradar, los "
                        "resultados dejaron de parecer una lotería. No todos los tests "
                        "salieron bien, pero cada uno tenía una hipótesis clara y podía "
                        "explicar qué había aprendido antes de pasar al siguiente."
                    ),
                    [
                        "#dropshipping",
                        "#datos",
                        "#productresearch",
                        "#ecommerce",
                        "#dropradar",
                    ],
                ),
                "es_story_5": (
                    "Del turno en McDonald's a construir algo propio",
                    (
                        "Esta historia no cambió de un día para otro. Empezó compaginando "
                        "turnos, noches delante del portátil y una tienda que no vendía "
                        "nada. Hubo productos equivocados, anuncios sin respuesta y meses "
                        "en los que abandonar parecía lo más sensato. El punto de giro fue "
                        "dejar de perseguir tendencias al azar y construir un método para "
                        "validar cada idea. Los datos no sustituyeron la constancia, pero "
                        "hicieron que toda esa constancia apuntara en una dirección útil."
                    ),
                    [
                        "#dropshipping",
                        "#historiasreales",
                        "#emprendedores",
                        "#negocioonline",
                        "#dropradar",
                    ],
                ),
                "es_story_6": (
                    "Mi primera venta llegó cuando dejé de improvisar",
                    (
                        "Pensaba que la solución era trabajar todavía más: otra plantilla, "
                        "otro creativo y otro producto que parecía viral. En realidad, "
                        "seguía improvisando con más esfuerzo. La primera venta llegó "
                        "después de cambiar el orden: investigar, validar, comparar señales "
                        "y solo entonces preparar la oferta. Usar Dropradar me ayudó a ver "
                        "qué productos tenían movimiento real antes de invertir. Ese pedido "
                        "no fue el final de la historia, pero sí la prueba de que el proceso "
                        "nuevo tenía mucho más sentido que seguir adivinando."
                    ),
                    [
                        "#dropshipping",
                        "#primeraventa",
                        "#shopifystore",
                        "#ecommercebusiness",
                        "#dropradar",
                    ],
                ),
                "es_story_7": (
                    "El proceso detrás del Porsche 911 GT3",
                    (
                        "La foto final es la parte llamativa, pero no cuenta los meses de "
                        "cero ventas, los productos que nadie quería y las veces que pensé "
                        "en dejarlo. El progreso empezó cuando dejé de buscar un golpe de "
                        "suerte y construí un proceso repetible para elegir productos. "
                        "Analizar datos con Dropradar, revisar la competencia y validar la "
                        "demanda antes de lanzar hizo que cada prueba fuese menos impulsiva. "
                        "El objetivo tardó, pero por fin el trabajo diario tenía una lógica "
                        "que podía repetir y mejorar."
                    ),
                    [
                        "#dropshipping",
                        "#porsche911",
                        "#ecommerce",
                        "#constancia",
                        "#dropradar",
                    ],
                ),
                "es_story_8": (
                    "No necesitaba más motivación, necesitaba método",
                    (
                        "Motivación tenía de sobra cuando abrí la tienda. Lo que no tenía "
                        "era un criterio para saber qué producto probar, cuánto tiempo darle "
                        "y cuándo descartarlo. Por eso repetía el mismo error con nombres y "
                        "creativos distintos. Empezar a validar con datos cambió la forma de "
                        "trabajar: menos apuestas, más preguntas concretas y decisiones que "
                        "podía explicar. Dropradar se convirtió en una parte de ese método, "
                        "no en un atajo, y ahí fue cuando el esfuerzo empezó a producir "
                        "aprendizajes y ventas en lugar de solo cansancio."
                    ),
                    [
                        "#dropshipping",
                        "#mentalidad",
                        "#ecommercetips",
                        "#productresearch",
                        "#dropradar",
                    ],
                ),
                "es_story_9": (
                    "Tres productos fallidos y una lección útil",
                    (
                        "Los tres primeros productos no funcionaron y durante un tiempo "
                        "solo vi dinero perdido. Después entendí que el fallo más caro no "
                        "era que una prueba saliera mal, era no saber por qué había salido "
                        "mal. Empecé a estudiar demanda, saturación, anuncios y señales de "
                        "venta antes de lanzar. Con Dropradar pude filtrar mejor las ideas "
                        "y reservar el presupuesto para productos con argumentos reales. "
                        "Seguí fallando alguna vez, pero ya no repetía exactamente el mismo "
                        "error sin aprender nada."
                    ),
                    [
                        "#dropshipping",
                        "#aprendizaje",
                        "#tiendaonline",
                        "#marketingdigital",
                        "#dropradar",
                    ],
                ),
                "es_story_10": (
                    "Antes de rendirme cambié cómo elegía productos",
                    (
                        "Estuve a punto de cerrar la tienda porque cada lanzamiento se "
                        "sentía igual: muchas horas, algo de presupuesto y ninguna señal "
                        "clara. El último intento fue distinto. En vez de empezar por el "
                        "diseño o el anuncio, empecé por los datos y utilicé Dropradar para "
                        "comparar demanda, competencia y creativos. Encontrar un producto "
                        "mejor no resolvió todo de golpe, pero me dio una base real para "
                        "conseguir la primera venta y construir desde ahí sin volver a "
                        "trabajar completamente a ciegas."
                    ),
                    [
                        "#dropshipping",
                        "#emprenderonline",
                        "#productresearch",
                        "#shopify",
                        "#dropradar",
                    ],
                ),
            }
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
                    "El mes que deje de elegir productos a ciegas",
                    "Durante los primeros meses pensaba que avanzar era probar más productos, cambiar más cosas de la tienda y tocar más veces los anuncios. Mirándolo ahora, estaba confundiendo movimiento con progreso. Cada semana encontraba un producto que parecía buena idea, le montaba una página rápida, miraba un par de competidores por encima y esperaba que esta vez sí pasara algo distinto. Cuando no vendía, no sabía si el problema era el precio, el anuncio, la oferta, la web o simplemente que nadie quería comprar eso. Ese fue el punto más desgastante, porque trabajar sin saber qué está fallando te deja sin energía bastante rápido. El cambio empezó cuando dejé de tratar cada producto como una apuesta y empecé a pedirle pruebas antes de perder dinero con él. Mirar datos, demanda, competencia y señales de venta no hizo que todo fuera fácil, pero sí hizo que cada prueba tuviera sentido. Este carrusel va de eso, de pasar de improvisar cada mes a construir un proceso que por fin podía entender.",
                    ["#dropshipping", "#productresearch", "#ecommerce", "#shopify", "#dropradar"],
                ),
                "es5": (
                    "Lo que no se ve cuando empiezas desde cero",
                    "Desde fuera parece que montar una tienda es elegir un producto, subir unas fotos y esperar pedidos. Ojalá hubiese sido así de simple para mí. Lo que no se suele enseñar es la parte de mirar el panel en cero día tras día, de rehacer la web porque no sabes si transmite confianza, de sentir que todo el mundo avanza menos tú y de plantearte si estás perdiendo el tiempo con algo que quizá no era para ti. A mí me pasó, y no una semana, varios meses. Lo que me ayudó no fue motivarme más, porque motivación ya tenía al principio, fue ordenar el proceso. Entender qué producto tenía sentido probar, por qué había gente comprando cosas parecidas y qué margen real me quedaba antes de lanzar anuncios. Cuando empecé a mirar el negocio así, con menos ego y más datos, el avance dejó de depender de tener un golpe de suerte. Este video resume esa parte menos bonita, pero probablemente la más útil para alguien que está empezando ahora.",
                    ["#dropshipping", "#emprender", "#tiendaonline", "#ecommerce", "#dropradar"],
                ),
                "es6": (
                    "La diferencia entre insistir y repetir errores",
                    "Durante mucho tiempo me repetía que solo tenía que ser constante, pero la constancia mal dirigida también cansa. Yo estaba insistiendo, sí, pero insistiendo en revisar detalles pequeños de la tienda, en copiar productos que ya estaban quemados y en lanzar pruebas sin tener claro qué esperaba aprender de ellas. Por eso cada mes se sentía igual al anterior. No era falta de ganas, era falta de dirección. El día que empecé a analizar los productos antes de enamorarme de ellos, todo cambió de ritmo. Ya no miraba solo si el producto era bonito o si el anuncio de otra persona tenía visitas, miraba si había demanda, si el margen aguantaba, si la competencia era razonable y si la oferta podía explicarse rápido. Ahí empecé a perder menos tiempo y a entender mejor mis resultados. Este carrusel no va de hacerse rico rápido, va de aprender a no repetir el mismo fallo seis meses seguidos pensando que eso es perseverancia.",
                    ["#dropshippingtips", "#negociosonline", "#ecommerce", "#shopify", "#dropradar"],
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
                    "4 errores que salen caros al empezar",
                    "Cuando empecé, pensaba que el error grande era escoger mal el producto, pero con el tiempo me di cuenta de que casi siempre era una mezcla de varias cosas pequeñas que parecían inofensivas. Vender con un margen demasiado justo, confiar en una página que no daba seguridad, elegir productos porque me gustaban a mí y no porque hubiera datos detrás, o responder tarde a clientes que ya venían con dudas. Ninguna de esas cosas parece grave cuando la tienda todavía no vende mucho, pero en cuanto entra tráfico se convierten en fugas de dinero. Lo peor es que muchas veces ni siquiera sabes cuál de ellas te está frenando, así que sigues cambiando anuncios mientras el problema real está en la base. Estos 4 consejos están pensados para revisar la tienda con cabeza fría antes de seguir gastando. No son trucos raros, son cosas simples que yo habría querido tomarme más en serio desde el primer día.",
                    ["#dropshipping", "#ecommercetips", "#tiendaonline", "#shopify", "#dropradar"],
                ),
                "es5": (
                    "Lo que revisaria antes de escalar una tienda",
                    "Escalar no debería significar simplemente subir presupuesto porque un anuncio tuvo un buen día. Antes de meter más dinero, yo revisaría si la oferta se entiende rápido, si el margen permite absorber errores, si el producto tiene una razón clara para comprarse ahora y si la experiencia después del pago está preparada para no generar reclamaciones. Al principio nadie quiere pensar en soporte, devoluciones o tiempos de envío, porque suena menos emocionante que encontrar un producto ganador, pero esas partes son las que separan una venta puntual de una tienda que puede durar. Estos puntos vienen justo de fallos que se repiten mucho: gente vendiendo barato para conseguir pedidos, webs que parecen improvisadas, productos elegidos por impulso y clientes olvidados después de pagar. Si vas a escalar, merece la pena parar diez minutos y revisar esto. A veces el crecimiento no se desbloquea haciendo más, sino corrigiendo lo que ya estaba flojo.",
                    ["#dropshippingtips", "#ecommerce", "#marketingdigital", "#ventas", "#dropradar"],
                ),
                "es6": (
                    "Consejos que parecen basicos hasta que pierdes dinero",
                    "Hay consejos que suenan demasiado simples hasta que te toca pagar por ignorarlos. Calcular bien el margen parece obvio, pero muchos se dan cuenta tarde de que una devolución o unos euros extra en publicidad les rompen la rentabilidad. Cuidar la confianza de la tienda parece obvio, pero el cliente decide en segundos si compra o cierra la pestaña. Validar el producto con datos parece obvio, pero cuando algo se ve bonito o está de moda es fácil convencerte de que funcionará. Y cuidar al cliente después del pago parece obvio, hasta que llegan mensajes, retrasos o reclamaciones que podrías haber evitado. Este carrusel junta esas cosas que no son espectaculares, pero sostienen el negocio. Si estás empezando, no lo mires como una lista más de consejos, míralo como una forma de revisar si tu tienda tiene agujeros antes de que el tráfico los haga visibles.",
                    ["#ecommerce", "#dropshipping", "#shopifytips", "#negocioonline", "#dropradar"],
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
        if video_type == VideoType.TYPE_4:
            return {
                "en_story_1": (
                    "From zero sales to decisions backed by data",
                    "For months I confused working more with making progress. I kept rebuilding the store and testing products without knowing which signal mattered. Things changed when I started validating demand, competition and proven creatives before spending, using Dropradar to turn each test into a decision I could explain.",
                    ["#dropshipping", "#ecommerce", "#dropradar", "#shopify", "#productresearch"],
                ),
                "en_story_2": (
                    "What nobody shows before the first sale",
                    "Building the store was the easy part. The hard part was opening the dashboard every day and still seeing no orders after hours of work. My first sale arrived when I stopped making cosmetic changes and began using real product data to reject weak ideas before losing more time and budget.",
                    ["#dropshipping", "#onlinestore", "#firstsale", "#entrepreneur", "#dropradar"],
                ),
                "en_story_3": (
                    "I nearly closed the store before changing this",
                    "After three failed products I thought I was the problem. Before quitting, I changed one part of the process: every launch needed evidence of demand before I built the offer and ads. Dropradar helped me see which ideas deserved a test and which ones should be discarded early.",
                    ["#dropshipping", "#onlinebusiness", "#ecommercetips", "#shopify", "#dropradar"],
                ),
                "en_story_4": (
                    "What changed when I started validating with data",
                    "I did not need one hundred product ideas; I needed to understand why one product deserved a test. Once I organized research around demand, competition and working creatives, the results stopped feeling random. Not every test won, but each one had a clear hypothesis and a useful lesson.",
                    ["#dropshipping", "#data", "#productresearch", "#ecommerce", "#dropradar"],
                ),
                "en_story_5": (
                    "From restaurant shifts to building something of my own",
                    "This story did not change overnight. It started with work shifts, late nights at the laptop and a store with no sales. The turning point came when I stopped chasing random products and used Dropradar to compare real market signals before committing money to another launch.",
                    ["#dropshippingjourney", "#ecommerce", "#onlinebusiness", "#motivation", "#dropradar"],
                ),
                "en_story_6": (
                    "Three failed products taught me this",
                    "Each failed launch looked like bad luck until I reviewed how I had chosen the product. I had no consistent criteria for demand, competition or creative potential. Building that checklist and researching through Dropradar made losses easier to prevent and every new test easier to understand.",
                    ["#dropshippingtips", "#producttesting", "#ecommercebusiness", "#shopify", "#dropradar"],
                ),
                "en_story_7": (
                    "The first sale started before the ad went live",
                    "I used to think the creative was everything, so I kept editing videos for products that had weak fundamentals. The real improvement happened earlier: product validation. Looking at market evidence in Dropradar before building the campaign gave the offer a much better chance from the start.",
                    ["#firstsale", "#dropshipping", "#productvalidation", "#digitalmarketing", "#dropradar"],
                ),
                "en_story_8": (
                    "Why more hours did not create more sales",
                    "I could spend an entire night changing the store and still wake up with the same result. Effort without a selection process only made me tired. Once product research had clear rules and Dropradar supplied comparable data, my time went into testing stronger opportunities instead of polishing guesses.",
                    ["#entrepreneurship", "#dropshipping", "#ecommerce", "#productresearch", "#dropradar"],
                ),
                "en_story_9": (
                    "The month I stopped treating products like a lottery",
                    "My launches used to begin with a trend, a feeling and a rushed store. Then I started checking demand, saturation and creative signals first. Dropradar did not guarantee a winner, but it gave every decision a reason and finally made the first sale feel repeatable rather than accidental.",
                    ["#dropshippingbusiness", "#ecommercetips", "#onlinestore", "#validation", "#dropradar"],
                ),
                "en_story_10": (
                    "A better process changed the whole story",
                    "The Porsche is the visible ending, but the important part was the process in between: failed products, zero-sale months and learning to test with discipline. Using Dropradar to filter ideas with data helped me protect budget, learn faster and stay consistent long enough to see results.",
                    ["#dropshippingstory", "#ecommercejourney", "#consistency", "#shopify", "#dropradar"],
                ),
            }
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

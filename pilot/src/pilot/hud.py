"""Conservative HUD pixels for the recorded 1280x720 GTA V safe area.

The tiny UI anchors below come from real captures, not a font/OCR engine. They
recognise only the evidenced layout. Unknown layouts and damaged anchors fall
back to game; text alone can never stop ordinary input. No history or I/O is
used in read(). Arrest and temporal flashing still need separate evidence.
"""

from __future__ import annotations

import base64
import zlib
from typing import TYPE_CHECKING

import cv2
import numpy as np

from pilot.contract import Hud

if TYPE_CHECKING:
    from pilot.scene import SceneText


def _template(shape: tuple[int, int], data: bytes) -> np.ndarray:
    return np.frombuffer(zlib.decompress(base64.b85decode(data)), np.uint8).reshape(shape)


# Source ordinals and extraction rectangles are recorded in lab/hud/README.md.
FAILED = _template(
    (16, 168),
    b"c-rli+Y*2v2t@b)f0~-HLUHkKFV&2r(TYbv0~S3ZvQ__cF4sQ~t|q3>Y&wz3)ved}>fh#+8BX2goshVdY~)kHY~$Ie"
    b"N6x7)fY}J+Bw;7(x_JkWCzxB0lLJh1^0e*dbQWNoAoV%Nd79k1bn27GCsBJ>OQp>F<0<X&EY+p->2prJ!iibVbP&?7"
    b"=N;zkn}nNd!Cn`!w=h6O&sW^^8<i3Nqw~JOxo+M8UCs|U",
)

PASSED = _template(
    (18, 96),
    b"c-q~PK@Na02n6T<pGFThg59E3@gN66mNKCL6q~J93Hbxxw)`FuqxiOop(xZh@A-y^y!lpch?RVV(|i=liAYhW_L+C9"
    b"9HUP7-TzeA3Cia99qJuEWqclw8Zp!9)z68^{U=vVe*a(dWytX;ukZ)!EU^WDmEKG",
)

PAUSE = _template(
    (14, 89),
    b"c-kG1*>6;37>EA|FZ9B2L%i_9#27*VH=wpd2e2&CR!Eef5JE(1Fo+S2xI`mMg-RlULMe1#W+~mRQwoK4Itv}zS=uvm"
    b"X74`j%$zyreDC|c-#GQjd;R41KK1wO>uT#7A2c*HHnz04wRf7#W~;T!+SLQ@zJY%pkBmGXTF7>}C+v2I)9H3Or*!#+"
    b"+x6Vzar<X{-dRbKLb4o|V^TC8PpmVah{uzO#61NuTHDgx+}zUI+SzHcSi8D=dV72N2KbNtwx=osq?GvL*|^>AbUIy5"
    b"mj)L=_q>>z_9@6+axhdNqGK=`OC*zX^9!r699x1&e2`tNVdt8fT3g$!ZRT#1#oXO9WO~#)I3hmk9iCu*cDKWZ``wO$"
    b")9s#hFR2^8B*)OSFCbA~xe=B_awHrDc1KRm&&?Mu1+$}>{GRZ%zVQkiYjyQbnM_gH);SumrySjbZhcZ5dN?{d@&q?s"
    b"Q{i)(ad@TdQfNxWvk?*W_#{atJAS>OEzG5r4Dqg5I+s(@E6XVkjYwM(KHO~5j!bf5CrMZJn=&C$&5X(j4?TQ3_B19+"
    b"T!g9+cOxni^Z_w}s%8mCqI3cd&#O&AA$*9rJE&{wP<k~3Z~?h-EkJMe-~VA+bZn~0Zv0L^EW=Buc?H*AJ5J>Tg{*N="
    b"GRf%W^Kg{Z4VU@35WG^w8j8%Zc$Dwr$79;LK%V|U{^le8`k9<Ll+6)*2Kf^?A8s9W5BvG6^;6yw3HJun%}=11G2=5V"
    b"AGAB&Nis|UZV&Pg1V1X#zJ$J8;w{awXe1-H(Wx2y%Acn{iGC9Bj>4~xt15?M%y~oe!@HR84B%Fq?SX?qsl>KD!(xsf"
    b"I<Va4n)EDkgBN*8jF(V8z{S2LDvO9t%i`Rks_nui2e0xAQO)Tx(e519jB7fBQ~3R`Hp8|w@`?ZyjScJk8XCg%o(GB%"
    b"%O<J(@wCskhK2xQ=>izC^l<t`<tpDFLv!!y@`|cl&y$7D1c<7Eu97h7@Ynz1+oB}MB<=k{sPMC$6O7*Y7K@`|#}pa>"
    b"_j|>`v6+yxhQ+f0rAxXYt8Bg9XwBk*c`)~_tfqyY1G+?2LF89;yh^l}!Ho$`V=xXoQf!tLjjfA!IDm}HXh`s#KCz2K"
    b"r9_qXU|23J4go7oX(b~4%^G%O`N2j0Z{J#4q3%87`O|bUfxH^&H<2&b_;u&HSfMh89`G`#^t0`D5ba|9=b~9ry2x!D"
    b"k2r$SXtq#?>4r76IHwJR_O^ltQ#wE<$LQyN(ke+w3#!(Et%*3{-bf(@3U(IQc%0$+3UA6dHleXg%E=&<%G~Hv$b+9u"
    b"h9V&qjZv-~Sj93arKdkWrLtq{GEbUx#><y<_0t?zlXAVrGrzOK@(P_5$PTpWY{Fi9_SQ|0rNtM0^y{U%ThXTW;6Pp2"
    b"bLUF!{YWA)H*d8pvVPl&*Rq_b|D|J58@H?4j8)RKSW_nVd<aLb+-pfH8LL-)@^`}m0|t=1t1$K-<ZIXB",
)

WHEEL = _template(
    (32, 34),
    b"c-jF#1i$;v&cDpY%h1@pI1w2rCJYKy+S}5qa#%@DM{t(K%FWm3{maS4!o9=Nk{lCjr@XM0JsU+)E)5M1BN+}91UsR_"
    b"*W&HT$iTqDx{?zeq3`<T>HfcC3JEl9tJCD&+rm{B9E{T2?#aozzq5}ZG^q8>wV|KG_uFG7c<}1Zu&c4?_MaI%%+%()"
    b"zP-Pm3o)Phw3wiyo~F6!;ciP!fSsG3ouAYFJ`~H;+{d@eyD%HC>%NzkoSc@LrlsQi!(>59ew>w^&H6PK&CuG)xyCLJ"
    b"m-fD&k&}>|mz9;5pStDsv{gT0k(cMpA5YHE*2Teb4_Cdsm~m@%Z)$K#ahQ#xr^M*XTQ-D|xKR;@%Fxrssuw(!n3Y;K"
    b"Pdy?I4HT4@m6es1m8y^{JUcNl3?{Y8)Xy{^grApzQF4!jazF_bl$Dj0m6esAdnr<MnyGOIKHAom1XHA)oRXH3nU#}z"
    b"8xxe4mX?;5mZeHTlg8xNqB9D<*f$=QkfEBQmW!L4o0BUOl$Vy4mX?;3Fk6<Al$V-S4ZzzLNTQmZn3R>Dk&&aJQxSrm"
    b"o}ODcHas7FnVpxKm?;q6-3wi*nwXlJnw6TLoSjDxU!R$XF@D3uH%y+Enx2FOTHezXRi2-mm6@BAl$M*NNCG2`o^CPb"
    b";=5rYR!T`u9}>>q**qejpOBWEo|Ki6nW{?$2~V4LHnx|Pe;h$kLPi=C&ehkd4p^L-nVFlEpPiYTLIwZ}Sb9NoU_2Zb"
    b"VCeA2h7D2X-1$lqfS{a|o0p%KnTs0%000s$FD5J~FD8GVsi2!9Ch^<->LDtHm6nu|i-Kw^2LuEL05B~lIXf><larK="
    b"m>wzZ-TnH43NVU!XjMBR4Fv`t695HwcV$>$Z-<wao0WJ4RN>?L`NRkaE^?Eqtc!hVReu@;0V`K@e20mOjEstV94y@8"
    b"<ofxi055Nbk+jV1(y5++5dZ=&M?X6`I5;>tHZTEN?BnA4_-YP-lcS%NkCT_5p<)970cXY1#mC3S#?IBaH8kz$*!uWi"
    b"8kCHam6w;Aouj5h00sgwoU^yOy1KZvyQ5AO=;Gt}_Fo%~nU<KEnxdSTgAy1u1qCf%i;j_$m6e{0HWTCA-}d#240)TC"
    b"n3|fHo{dEiREbj*1pp2h940F;GAjX4>Eq<|^x+sNnUt8BnV6V#Hd~jOno=JH3JVJh3m6LnCdKIE+4A!5dl^EMn3|cJ"
    b"mxPa)nVXrJd~H`eH!UU*BXZ>E+T`E!^Yi3$5D`0ihL4PfgM@ZnQ#~ve5d{n%Nte*v=jG+*=J@#a?%%pe6&4#C8W<H3"
    b"5D^kAGfrTax!l~@?c(X=<m2M``ug?q=Ihm;gk))SdWo92!q3y#+2q{X;pF4s<mBPu;Q9FN?&;_5;^pGs-rU>S*VEG0"
    b"+}6zH<>ct*;NRrp;NRc={5S&",
)

PHONE = _template(
    (14, 48),
    b"c-k$J%TH556o=2unYs7&+6#p$0`b9Hz)C;@fruy)e9**(poO5=02YH#Aexq9BW(qN6etv;#_OX-DsfT71u-BdCN6NJ"
    b"iCYuJjSK$_=c2QjWX}1WGs*W+j;JXr18Oo+8G%svcQlnyR6*ig;tUxQf&>sKBH=X_0FrJ>1Cj<z1Sk`g{PTT<04Oss"
    b"hV0Ifz)A^$l9_zaNSCw2TI@0d2P#W|m*2kGS};>0+Cgk504ihPqm-%6NOhL^Kx6N$!#!P?T~(&-vz3%?bRFz@<>1z1"
    b"kdb4pIBR8P_KQa<zY!pNm!reaYis;ti-APYI~krRb;svC-@~Sya58I5H_s+wOG)>c*o!rP?6cTYzFv_M8lUP2wmBX)"
    b"N9*=`ee>-pMf%Top5aHWJG%YT$54T5D=|~Q{9w&5K6}+`RVQLknih*)e&>p(e|{vAr`qx==QsVUv5m*^#MjqzYtO!{"
    b"M^}Q|^}uuQ+4=E^KIHUeMjCEjIdsYGZ8JG^nGfnie<njeruvdOC&%KeRZY{wA5thO*GIbi-LvhzPp`im2#h)dgHaoC"
    b"{vKF(f3){kb<d8iZoB{P_?_hK`=Rh=B|vVcXQ(mrTKPH8X;;e$&y5CKrv);6@$n*7(Jh^7k+N@%wiX-?1e;SYOw<Bl"
    b"iXs7|QOOJnLxGrSG69wf)QqVtoukC|s1}P%G>yv&5CgvOfEidg3igyxL0wqDfm2E0oEtrYE9^Q!5l~1Vuu|j%ndqiQ"
    b"fH8&&m1Qn&VUKW#anAnRC2~X@G;|`n3#f1mCFCM23dVym1pfji1&Qb",
)

MAP = _template(
    (20, 40),
    b"c-m!<O-L0{6oB8)_}<g`yEAw0%)Iwz-g}yYmWlreMn$^{b<-l+NQ9F4%tUGxv<Rtn3#s-&M7an=aM7xu)~#9vZG<E="
    b"_07!vovuZjIvg(d9=`K&?#X1b*<9w|$jZ!SGk?$HOD>l${Kw_~5R%E|mHaW9&nu;pnE|L;_I=$okyFh6j$=n&W(U;E"
    b"z=n#_)>i6V-^G-1A#hBhz4fl5v`K;9uGXLKF+#B5g+j4y>fkUYoTr?8|NODV#nFYLrl|!*QKnh^ZRZC|1yfZ`jnZd>"
    b"BIPMPIE%dCji9`t>$(O&Akqo5L$%NCFas#3dGt7BDHGya__cKzr9#vUUDIu4gz(1X_SW;^@zj9DA(5<wjB|m<?h5ur"
    b"Bb-$=$$_>pM*UfyrW;ypI32?buT?2$obJm>E?JbYKsQa(DvS{t%<gl#8pH-tM+kXXA)I1L*{9*~1CyKqEMS@An1<Hi"
    b"$-eA8YNFBzrH?8!O(~71-04VqX=qrMWf#X|>i68ZI%CXnAbphGFN>IRd<AXcpPV!4v!qWQjY<7x!uZSphK@GM#1n7x"
    b"?e+%oFTUS={SM2$n6_;KFdE^;@?n%N^d^q2j|lRrv$wmy@5N+&p#RiR!bR6HXWIP{IsYI^;+NAH0i*jckt5+2ZAEf*"
    b"M+r|wuVG29G!bzo62UQ{t_f<CP?E%iP$441cpOCyXhRcp^z33ui5A7Y>^N|IVR7;L+|tVO;!1O&x!PPh11;OJZA%-P"
    b"Z!XT?Y2I4CUGWff4Yyqb5JJm`W!DK!->;N?<Tysbb=p;1m0eX&z9F<NU?bP7RKr@W9tM@b_Ygur{#n+c*XXI1J=aB!"
    b"4ISipel@7c2qahWWm)dV1eSyR#))5cwKNj",
)


# Native 1280x720 masks from the real P25 frames; see lab/wanted/README.md.
STAR_RING = _template(
    (24, 24),
    b"c$}?|3km=r3_^SNzjUzZv$=vIi7<82N_hrc>5v=P$@RoQbQ%KH;hizwu~sHMT|?3-<fz;Dyw-T%DCqPwu4euRZzNlNK?P(v09*",
).astype(bool)
STAR_CORE = _template((24, 24), b"c${Nk7_@+qkt*Vhj2IG($N+~74lP)X$7VBL<(Lu>5iH^;)ZhaEOOyaa").astype(bool)
WASTED = _template(
    (30, 172),
    b"c%1E(;SPf^2!#9oFU^)^%b?srZPnJK_oFcg$7iKl%GTCakL0b{46Tv}!QR0dcaUa;1FZ7XcXH&vs<61Q"
    b"=oDil&a~~)h9gu%sY#?x$ys3ujxtX~JBJl}+Bln*l-1odf!xU^Fz1A|YC{=9o~EbvCxNW|parGwiSrpK"
    b"yd-~DU;~cL>xHbJs^wY9sPwU#FWoq6)oO$lmlnM`mmmO+W0i2uzPjr$>{v+&+*e?vQ#x1$hv%{~C=4;g"
    b"+VZ;utOXgUFzXSrI#b>%IMP?DVqaOw`&&xSWSvd2wKY#KL?RzV",
)


def _wasted(frame: np.ndarray, banner: str) -> bool:
    # Require both the actual glyph layout and a desaturated scene. OCR can
    # confirm weak pixels, but cannot cause a stop on its own.
    pixels = frame[292:412:4, 296:984:4].astype(np.int16)
    chroma = np.maximum(pixels[:, :, 0] - pixels[:, :, 1:].max(axis=2), 0).astype(np.uint8)
    if chroma.max() < 12:
        return False
    threshold = 0.76 if "ausser gefecht" in banner or "außer gefecht" in banner else 0.84
    if _score(chroma, WASTED) < threshold:
        return False
    outside = frame[::16, ::16]
    outside = np.concatenate((outside[:18].reshape(-1, 3), outside[27:].reshape(-1, 3)))
    return bool((np.ptp(outside, axis=1) <= 12).mean() > 0.9)


def _wanted(frame: np.ndarray, game_hud: bool) -> tuple[int | None, bool]:
    # Slots fill from the right. Pale blue silhouettes have no black outline
    # and are not lit stars. Never carry a count across frames.
    gray = _gray(frame, (1119, 34, 1219, 58))
    hits = []
    uncertain = False
    for x in (76, 57, 38, 19, 0):
        patch = gray[:, x : x + 24]
        core, ring = patch[STAR_CORE], patch[STAR_RING]
        contrast = float(core.mean() - ring.mean())
        lit = (core > 105).mean() > 0.85 and (ring < 115).mean() > 0.8 and contrast > 75
        hits.append(bool(lit))
        uncertain |= not lit and (
            contrast > 90 or (contrast > 45 and (core > 105).mean() > 0.6 and (ring < 115).mean() > 0.65)
        )
    count = sum(hits)
    if uncertain or hits != [True] * count + [False] * (5 - count):
        return None, False
    if count:
        return count, False
    # A zero needs corroborating gameplay HUD and a readable empty corner.
    # Bright white clipping and codec block edges are not evidence of zero.
    corner = frame[32:64, 1120:1216]
    if not game_hud or (corner.min(axis=2) > 235).mean() > 0.7:
        return None, False
    values = corner.astype(np.int16)
    dy = np.abs(np.diff(values, axis=0)).mean(axis=2)
    dx = np.abs(np.diff(values, axis=1)).mean(axis=2)
    if (dy[15].mean() > max(20, float(dy.mean()) * 3)) or (
        dx[:, 15::16].mean() > max(20, float(dx.mean()) * 3)
    ):
        return None, False
    return 0, False


def _score(pixels: np.ndarray, template: np.ndarray) -> float:
    return float(cv2.matchTemplate(pixels, template, cv2.TM_CCOEFF_NORMED).max())


def _gray(frame: np.ndarray, rect: tuple[int, int, int, int], step: int = 1) -> np.ndarray:
    x0, y0, x1, y1 = rect
    return cv2.cvtColor(frame[y0:y1:step, x0:x1:step], cv2.COLOR_RGB2GRAY)


def _colour(frame: np.ndarray, red: bool) -> np.ndarray:
    r, g, b = frame.astype(np.int16).transpose(2, 0, 1)
    if red:
        mask = (r - np.maximum(g, b) > 45) & (r > 100)
    else:
        mask = (np.minimum(r, g) - b > 60) & (r > 120) & (g > 120)
    return mask.astype(np.uint8) * 255


def _screen(frame: np.ndarray, text: SceneText | None) -> str:
    # Colour AND glyph shape are required. This does not confuse red death text
    # with the evidenced mission-failed banner, or a yellow car with success.
    banner = str(getattr(text, "banner", "")).casefold() if text is not None else ""
    if _wasted(frame, banner):
        return "wasted"
    red = _colour(frame[292:372:4, 296:984:4], True)
    if _score(red, FAILED) > (0.76 if "fehlgeschlagen" in banner else 0.84):
        return "failed"
    yellow = _colour(frame[116:376:4, 440:840:4], False)
    if _score(yellow, PASSED) > (0.76 if "bestanden" in banner else 0.84):
        return "passed"

    if _score(_gray(frame, (204, 76, 390, 112), 2), PAUSE) > 0.86:
        return "pause"
    # Full map has its own zoom-control glyphs and a scale at bottom left.
    if _score(_gray(frame, (600, 658, 648, 686)), MAP) > 0.86:
        scale = frame[601:607, 65:203].min(axis=2)
        if (scale > 150).mean() > 0.15:
            return "map"
    if _score(_gray(frame, (622, 440, 664, 480)), WHEEL) > 0.84:
        return "weapon_wheel"
    if _score(_gray(frame, (1088, 428, 1144, 450)), PHONE) > 0.86:
        # The bright logo is inside a dark bezel, with green side rails.
        rails = frame[460:640:8, [1031, 1201]].astype(np.int16)
        if (rails[:, :, 1] - rails[:, :, 0] > 12).mean() > 0.6:
            return "phone"

    sample = frame[::12, ::12]
    if (sample.max(axis=2) <= 10).mean() > 0.995 and sample.mean() < 4:
        return "loading"
    return "game"


def _fraction(values: np.ndarray) -> float | None:
    """Fit a filled prefix, rejecting islands typical of codec damage/icons."""
    n = len(values)
    # Positive values vote filled. A valid bar has one left-to-right boundary.
    filled = values > 0
    errors = np.concatenate(([0], np.cumsum(~filled))) + np.concatenate((np.cumsum(filled[::-1])[::-1], [0]))
    end = int(errors.argmin())
    if errors[end] > max(2, n * 0.12):
        return None
    return end / n


def _bars(frame: np.ndarray) -> tuple[float | None, float | None, float | None]:
    # The track remains coloured even when empty. Chroma locates the HUD;
    # brightness relative to its translucent surround measures the filled part.
    band = frame[676:680, 64:244].astype(np.float32).mean(axis=0)
    surround = frame[[672, 682], 64:244].astype(np.float32).mean(axis=0)
    r, g, b = band.T
    sr, sg, sb = surround.T
    green = (g - np.maximum(r, b) > 16) & (g - np.maximum(r, b) - (sg - np.maximum(sr, sb)) > 10)
    red = (r - np.maximum(g, b) > 35) & (r - np.maximum(g, b) - (sr - np.maximum(sg, sb)) > 20)
    blue = (b - r > 8) & (b - r - (sb - sr) > 8)
    yellow = (np.minimum(r, g) - b > 35) & (np.minimum(r, g) - b - (np.minimum(sr, sg) - sb) > 20)
    # All three differently coloured tracks establish the fixed geometry. This
    # prevents scene foliage or a billboard from being read as a health bar.
    health_visible = (green[:90] | red[:90]).mean() > 0.8
    armour_visible = blue[94:136].mean() > 0.7
    special_visible = yellow[138:180].mean() > 0.7
    if sum((health_visible, armour_visible, special_visible)) < 2:
        return None, None, None
    corrected = band - 0.25 * surround
    health = None
    if health_visible:
        channel = 0 if red[:90].mean() > green[:90].mean() else 1
        threshold = 165 if channel == 0 else 150
        profile = corrected[:90, channel]
        readable = True
        if channel == 0:
            # Red damage flashes can colour the entire translucent track. The
            # available red frames have no stable fill edge: never call that 0.
            low, high = np.percentile(profile, (20, 80))
            readable = high - low >= 25 and profile[:12].mean() >= profile[-12:].mean() + 25
            threshold = (low + high) / 2
        if readable:
            health = _fraction(profile - threshold)
    armour = _fraction(corrected[94:136, 2] - 155) if armour_visible else None
    special = _fraction(corrected[138:180, :2].min(axis=1) - 155) if special_visible else None
    return health, armour, special


def read(frame: np.ndarray, text: SceneText | None = None) -> Hud:
    """Read RGB pixels without OCR, state, input mutation or external calls.

    Unsupported sizes/types and damaged regions abstain. SceneText may be old;
    it only confirms an already matching banner. Wanted counts only evidenced
    star shapes; the flashing field makes no temporal claim.
    """
    try:
        if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
            return Hud()
        screen = _screen(frame, text)
        if screen in ("loading", "failed", "pause", "map", "wasted"):
            return Hud(screen=screen)
        health, armour, special = _bars(frame)
        wanted, flashing = (
            _wanted(frame, any(v is not None for v in (health, armour, special)))
            if screen == "game"
            else (None, False)
        )
        return Hud(
            wanted=wanted,
            wanted_flashing=flashing,
            health=health,
            armour=armour,
            special=special,
            screen=screen,
        )
    except Exception:
        # A malformed frame/text must not interrupt the conductor's input loop.
        return Hud()

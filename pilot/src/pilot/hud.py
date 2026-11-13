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


# UI-only supports and provenance: lab/screens/build_anchors.py.
PAUSE_UI = _template(
    (14, 46),
    b"c-obcJ!=(F5Qa}BScrl}FbQT=ghU9K##kg5)<lqOz(O!!!2AP0K>t9jB?c_4jFni~27)Q<0+u!*U=v~?-efQC&Kb^pobl|Hm2LBu"
    b"XCCIv`_4FbDjks$0FtPI_lS7VR{Bu-{eJC{RikiS9y<41RF?O^)J|T^M>8v1n$#X#x;8pdd^cQqh#rG;UIntvS~R}8c$HG`(9#j?"
    b"-s1M>5BD#_qqD2%B{noe_NLaTf7UY!NgaBA)q@?K-yY=oF{(O;k>L6Uu(G|sLXBG5z-}!Kto(H52jq(wl+$#P{p4#%UaO6ale+ZM"
    b"xw#v&W6Ny$oyaj&f-z2gL{y-+7n;`o|0K2bvga$0$L}KMdHNmy(bJnUu!`S}HZ-=h*0EO{lV6`y>-8+9F{H!Hldrow-)w7~sN+&V"
    b"<_d4JHDXp27O6^^nDETR&D&Eit1q+Mb*ZS&o{HJt0@B(V4e1y;?Ml*)LUI^7d0VY%S;~P#m_?e(uO{L^LlDse9JX}%^Q402F(fm-"
    b"7U-YurrcllI$RV",
)

PAUSE_UI_MASK = _template((14, 46), b"c-muNAPF#H0DLl|sz<77k^lfA+5xc").astype(bool)

# The glyphs and their drop shadow as five pause menus share them: the cable tour, calibration
# frame 2400, Wi-Fi frame 8196, and two from Remote Play on 11 November, by day and by night. The
# template before this one scored 0.71 and 0.80 on the two live menus, under the 0.88 it has to
# reach, and the waypoint skill backed out of the menu it had just opened.
PAUSE_TITLE_UI = _template(
    (28, 178),
    b"c-rll;gZ832!!|jUwS)pZBD>NB{9>RUj5ND5z424fdc<xkgE@$6Y11>fZA^wX&z%r%nQpnMBBB9TqAx-hiPdsqj){0yVjOWVY)=j"
    b"Hxgq`jO)bgE!{~>rG!1iEgosS&EzH$cXBS$omwL{=7UliSXT2_hrP*=XhUN2{S2`Z7e|I&TibCT=PKq^J_u<M72T}5nG;W}&*J#l"
    b"ECih{^O{!^VnkxD6Jt9uZNdm*l!*b{OpGEiBQf&`{X@hU6SpipL(HwjSRv*`;-J5sIG!j!)~@X_=X=b3#Cy()w65q~@R7tE5i_GK"
    b"5@%6i$ySM7irq!boESx7cw+7*h9u@XG3Ue-am;Z&G$xMv=-q1kVQW6~nRQvdG@PZzpxW%^VmqmceU+*^Pl{HJa0iH~u7s7m(Y0$1"
    b";TVa{%PUklqN&>c55jkR(s%&+8*kS",
)

PAUSE_TITLE_UI_MASK = _template(
    (28, 178),
    b"c-rll+it`l3`A%C|EH^JL$Jp-)Fgds(MriC1`fVq0{n?a{`BGJMfvI+pf{$G=4e}DK3K*Oo!2IEkNErL=eH%UD6YpeSE9FMBg{F@"
    b"Qrf@fAu)~7dc+BTO$^S<Au(m9UnXYO3GWb3f26TCi$4gq5;^DT;!AMOH0(^B-4lb(N$f<7Q%ayMiOv0rm<4ero}>(Lu5Co4MrIbJ"
    b"hSJK>_PLpSj!~bvWa2E|u~hwIwPqOWHC*^Hr?Oy(^T>k`)1(#6F7|OC4*BCIp{{jF3>zC7n7oOR5~EG*HY+CgWv&?RK<R^!Dwf1h"
    b";yLQw+b`oWF?Pgg5*xp&i2d&Sx{h1KaAiP2%!kBUZ=}RLCDtxZRi`>;&~X|`9b(qRQ&Go$EE;jd(FAA2x_>>6yghNpk7<czx41T)"
    b"=fpBUrE+T#a}H1tzmwf+jUgvSx`Tu)hL?$v5;Jj>f|%(pNuQn7kG<`*(%2Gfe^C;=Jt!I6<*j%GkkW7$%yqSy$k87slXDvx=N}Ks"
    b"L(4qunvGCG!xxRL54wKM&bUf!%qvw+0M^<sJ+H9!wc??mO(a$Cw?BIPx3YZ!p4$dW",
).astype(bool)

MAP_UI = _template(
    (15, 58),
    b"c-muN7$6{&%}s``nPm(N9v@5@7$%kzuZiuT00V>7MJCqC?;06-f66mTrIlK<GBBy<HR>9xGDH~$m-;{)BNNMD5*%4?&kW-5B>89j"
    b"U#i9+_MV^XdBjr&ng7D#UrJmqm9eP4&-dK($&LB$_X@A|TNq0E85oowGADkDbAD$H)W|yFrFhW4SuzYP*9{e4i#!+d*dnmIj)PP8"
    b"liJ<{Hcshx0Suq3*qDUh7$+>?U@-g6T(yvaDYJqhe{%XKB}UFqN<b&4mS;9H%=KIp$nxp^-c3jTg*;UUik|W0{A2;Np*b~iE)#?P"
    b"2bRWSu)FiWe|pcs!1hfJ$X5FK!kp3W+J8mPFX3Fm(r!|3j2Rg?{(CTd^I>4%*z1|Fl!3wGH48Ls^1tb=>|o;hrVM0re*MbNAoA%M"
    b"Cqu${F>dcKJkby3Iii2LF}(Sp%H#W;Tl0fF^IEvh>?T%`x26owg4uwa&VFVF)@|tw3|#5^*6+1oW=%Y@rvJ4Q<GYT{tG634Fx2c@"
    b"K4S_}lrXt&Wzf6gi6ye6L^zlPf9f-TQ)J*|A}MXuoYhrqy(q~2UX#>R#g%#X!gMhv#v~q+6C@*1ssP3IlOq",
)

MAP_UI_MASK = _template(
    (15, 58),
    b"c-qC1O9}uW2t;S@f9WU+bee^^Nhm3N{((<IvH{HNoELHtS@h>v>f<JjB$7=s_^_4`EvX_$cR`TLm5PfwE6G5jLWbVPU2r|yu63Gr"
    b"`Yuj=L3$)=&;X-80iO",
).astype(bool)

WHEEL_UI = _template(
    (33, 35),
    b"c-qC&Sx8h-7zgm{n9EqEjnU!)W`=9&nERxbX_;uGg(=g9Efxc%4TYj6W8;!(cjhkVo^$TZ+_{$K(4rRQm?2>xQ3};d5rl0>i?mP?"
    b"1wk_|qZatu|Gb=sALskdMiA492?<(H%$;Ta5liP5$J=l8!}N){kAGl5;NKvW8vF6-^LOiRKd+QB@yW>Rk)Gn&Vr|>6N1bND`ti9c"
    b"qV(n19qV=L%P-_Ca{gPtAec<t)zQ(iwDd|NHqe&)Kex^hUGE245rPmHE$@EzD--jykkt==kDV6O7b^gOr71nhxAlJb-K*Sq7}BHn"
    b"raRt$t)HqmRAS4f5>h9EzON69H#C7BrRS7LHj>~#a$fv$DY2NQ7>+~mN>gNfYE+E(6w%=3x||BSQIoaE4<jB!z+6;^rB|6PC6glG"
    b"$Qqbt05Luj=!+pjfTAw!h|>+cde)INLA1gpEYck0#O7!j&DaJ-)yek)fn$ZdagoKhn(f==0B6dPYB&buD->&1mYYl%;-GP|^Sr<#"
    b"V2_Q=FGA>Sa_yZ#c>zsxxMreGwqS42ek?XZ1nI=m_!m!mN<y;patebd+vPc%fPiJ8jkp(>%H{2?@Kj{#7DcAtBq=f@ZoCj|OCdbG"
    b"a;wsg7N@LQvhU5iLCw^;Xw4>DVS|8mK7_<w78SB8bVZ_Xxp-L+!zW3khKDTKTz5R$TjK2I6cZehkeZN9n=tJlM6y<WWc!w&<sK55"
    b"x3g<y)js8sV>K+#87m#v=&Cr;*xjiuE6gchA#n-MKUvezP+zaDR{J|hn7STxjC_9E)l%y%A>uYGlI)39%y=%9yvQ3xEMj!n#fdmL"
    b"@Ob#a(9rOMLCfkXA!Azsi443TikS=MIVB0*H*fXbzTJ1%lIvJS#{v#vo=5evr3z2im_2%$VHlQeNpz43lI1Zn0w!aTQnziPlXP)#"
    b"Sahsh9z5f9Hv%3(4yzK1b$W9_fQOrl)MLJM))z@SZNEmcfu=YE(pRf?Wvq|;=eK66TFx|`BP-OZUF+ll#DB>jUF1sf",
)

WHEEL_UI_MASK = _template(
    (33, 35), b"c-qC&K?(pM2t?8O_rG-Qf{-Rq>#rZ`Mrp-N=RARBh&VxBYzAwv1WT}l3If)6LXupcq8idaMz0CYi}Ej`^E2v81AW8-#s"
).astype(bool)

PHONE_UI = _template(
    (22, 49),
    b"c-muNARRDzWJE;(K_oJWii(bnjg3PBu@T|kLSPMLk6yoi^Y-oAcgW!V`wyQ!efo?5U%q_(_N<Kwq+!vcM^|nD!A)dv>(=eNckkXq"
    b"0(WoUe0U11A!z-TGpB&yG%`4I=Ir_N=Pw|G+ZT^Ef;BM8g=IzqK@@%vmy%}A#V~Au69)qWixd|pBO@;}OpH|_AyE`Vr8qB$wE4lw"
    b"z`%SYa)-ImDORWqSM2vM-=FiLsb}4r1ELn5_SECxPl$dWwCs+ckhLzikerIy`+UxYzswofH5jE;r0ty~IMsr^qzu1j0@aKC{c-4L"
    b"Q1PC--){W5+;MB$H<RhVejfNfPgZ5;Pn9Eo*l+)T_2<_btDnFBt@!@4AE-h9hduYh^<N5}q$Yp!{hcWGVe;ofeziA0KTKZrFXZR@"
    b"u>U_FOD+2Sb)VX;??3kdV@_c976#4_yT3%f*Pbw^^7G-tx7NHDma`Bw|M26`zn{PU{(b-b=l8$={(k-bd+$#xkc&R}Gy8r#w4(Na"
    b"=<o3B4Pp@`yE{4S{|d3K`MK)XztexuF8Z!(w(i$29hbecehLFMXno&Y^0nx7%%<B_UwdvIPkG(`!<ZrEbNBim4wHVnuKg|@^{ME^"
    b"xgGyXzwf;K(*vl%qP}CUDPOBZ=uG#yc~&c?+3R(4GKd{`yVr=(cQ#*oErZPN=k3yxho58%MZNWggf25U(K4{GvM{kg0-T8v2$1q5"
    b"0}Bf)BLfpZUD6Q%VXjZr",
)

PHONE_UI_MASK = _template(
    (22, 49), b"c-muNARRE007z92)<Js>B>Q1l0I*-seTCJJh+xIgz(_#D;EHKR+G@bzA_l5zfQ2qfT%kt^oS;WS0stC{0%r"
).astype(bool)

INTERACTION_UI = _template(
    (17, 143),
    b"c-rljYfMx}6oAit?q&DhyDt0SvMh9$g`%=)EUg55U}#IVX|O32OB)aYOAOYCQG*(j+SpLFw8$g2X-%xDNn2VPZCaE1DnSW^SZZ4^"
    b"YsG2=BgQVQ3%i$nv7Ol~i_|9l(;xle{Fr-Y&di+eoH=uH0UouvjZPK}k5T^{9PU=dmUI6#4#!cd=$D~q=MoGLnBm2FionvugF96V"
    b"=V|T6nNi{n3YOGiDY;b-(AL(r4?x$@&=A!cTMhu!=L$$9@>}sHGg=Q+VG9zQo0?Gn<R%hGLrvGkBQKHwro(n*jHp};u=H!^g*pkC"
    b"`X&x7BNu#{2fBj?0S+E1hr)Wa7Nka=tj?O_mVJVTH-l?1*pv>S?uKh4fOfPaN(gDw^#BdyJF$1yf-j>pY#|Y-^}*-R%%Skds4pGi"
    b"2<z4Ef&~@sW(`>U!#n`fSp%7#y^k;JIZLu5{t^v9+$sM$NC@mfChAr|ja-X@X`M7u*Ngs!1F(5)%nXns$0NU*zCgZkck{@o*5XBT"
    b"Y_1!{En~91CyK*RRdS9RDQ)s1)K}i7h|Vwd6bN=tF<2w_cB1fgR>Rw!YGCaXHrhG%4T~b-nXG^`pQu>fBu}KXkmUad91gZ`+kaXM"
    b"Mt33_f6$Ix(ahk?_u;v;hy>IpEomM!u!h81c|}w!MUqhe+A!zv+i}J)WiH+pDU}_B`fLqszbCOkr)&5t?UPm@-?%im7Ser!Vs&@("
    b"-U|ZE3mEB#aByPro+{GfLotB&kD`;A*kw&6@ofBiE(Szz2It&JK}zV5+@(?yYbpa@)*w-IO|fE&=u^C6?PZQUT?_i&iPo2%;t1k)"
    b"@tHD~?0@xC1tbREnz3sdFC|R@Bl8drc8pvso8v=TjPp6hxp}T$xva?5>jR_S0vc8ZC3eFk1Idx$Qn@6`V+^LDzU+5RX+Nu&2<yzU"
    b"zz^;cx;6t%=j{2`byP*W^IsUCQYWPDO0WhSV}>2mW=q&W55Iy3A8wn21F-+ACxVt3&fOd(0BNDTti?Ik8iDyS+}}SI%3_m!4!%UT"
    b";M+1pamq*7+-VbD%;W?$<|&a)_h%okrFjl0A~l!~-e+unQ{{1WcQsfiw6o>!-4hOvUUg?R9vs^m!(pOd?H}LEN_0>r(&6Qb);5LS"
    b"30vr;B)Qn`$m~1JW=!)ybo4MWoQfN?&Rc_h(Dd#jtp0c)tFE}q)hE~Dir_3!g`X!+?i*M}cCQC(*fe`D)KI6aqfZ>bwdX=r3`Yqx"
    b"^Q;^;#&E{UlguWgg^;Fk?6N0?>Osu4+^w|*RX}K6^;8UJgl1m%*6Q@BpIsHe9z+SK=?$%;wu~>ah%2Wu<HD=h)qy)Ag>eFlk`_qT"
    b"L<Q$*x5q-P`ZLd9Ec7kBk0X7@-j{a&iXTeFE{t=s?}u~ef9f%tJ8=oi>M|b9!%O1(tkymRNMu}|k8qrL!}4QjL(ZAoL%+R)F57m|"
    b"fYj+jMWEU-<hnVq22>rnknr<Xk^QIu^h1}r&v*TDKT%X0MpHpm;=FasxpbzM6D%`Rt+Qw2NNH(Km5o68s8(cXO*Di8#|gObvucD%"
    b"@%TX*)HsiX_!KQpH;shVYCTdjtVL2AfyzW8&nf2$EX~E~W)esg<B;oWgF($b`jz<i_7{<Bf1L",
)

INTERACTION_UI_MASK = _template(
    (17, 143),
    b"c-rli+YZAp2t&>P|Mav;4K_FzRePwW@ldrim=j7U@He&i*l*)pnxtIPjE9n3ao)G26m%sYhEF{y5TWtI7ZlDfePOQ1HBOAp=6cb*"
    b"@_L*wII+ZubDXd^P$)%Wocxe`92gvMXwoQ-uamMK;uKBA(Y>=oYk-DRtTp;=oQCyPob;#k5l&2c$1TPR2TL48KgbMcj!!LYr>LQ*"
    b"gNT-GaO%w9HWm?+a9UAmmsagMEO$8Q!>-I2$f2H`1IakU@qLyQw!@Sk&c`3g<$l;N^uhK5+5ZG5",
).astype(bool)


def _ui_score(
    frame: np.ndarray,
    rect: tuple[int, int, int, int],
    template: np.ndarray,
    mask: np.ndarray,
) -> float:
    # Only printed glyphs and their opaque outlines participate in the score.
    # Scene pixels between letters are deliberately absent from the support.
    pixels = _gray(frame, rect)[mask].reshape(1, -1)
    return _score(pixels, template[mask].reshape(1, -1))


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
    # Codec block edges are not evidence of zero. A lit star keeps its black
    # outline in front of a white sky (darkest pixel under 25 on all 214
    # labelled stars), so a bright corner is empty only with nothing dark in
    # the star row.
    corner = frame[32:64, 1120:1216]
    if not game_hud:
        return None, False
    if (corner.min(axis=2) > 235).mean() > 0.7:
        return (0 if gray.min() > 200 else None), False
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

    if (
        _ui_score(frame, (862, 665, 908, 679), PAUSE_UI, PAUSE_UI_MASK) > 0.88
        and _ui_score(frame, (207, 80, 385, 108), PAUSE_TITLE_UI, PAUSE_TITLE_UI_MASK) > 0.88
    ):
        return "pause"
    if _ui_score(frame, (1129, 665, 1187, 680), MAP_UI, MAP_UI_MASK) > 0.88:
        return "map"
    if _ui_score(frame, (625, 443, 660, 476), WHEEL_UI, WHEEL_UI_MASK) > 0.86:
        return "weapon_wheel"
    if _ui_score(frame, (1093, 423, 1142, 445), PHONE_UI, PHONE_UI_MASK) > 0.88:
        return "phone"
    if _ui_score(frame, (68, 111, 211, 128), INTERACTION_UI, INTERACTION_UI_MASK) > 0.88:
        return "interaction_menu"
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


def _health(track: np.ndarray) -> tuple[bool, float | None, bool]:
    """Whether the health track is there, its filled fraction as drawn or None, and whether the
    track is green but dim as a whole, as the HUD is while the picture fades in.

    The fill is nearly opaque and the empty part translucent, so neither has a brightness of its
    own: the bar ends where the track steps sharply from the fill's level down to a clearly darker
    one, wherever that is. Map icons that slide over the bar are white, black, grey or cyan: their
    columns are left out, and the bar goes on where its colour does beyond them. When a hit lands
    the game draws the fill pale yellow and the lost part orange for a third of a second; both
    still step down in green at the new end, so the first frame of a hit is read.

    `track` is rows 670 to 679 of the health track: four above it, two of its rim, its four rows.
    """
    pixels = track[6:]
    r, g, b = pixels.transpose(2, 0, 1)
    high = np.maximum(np.maximum(r, g), b)
    reddish = r - np.maximum(g, b) > 30
    bar = (high - np.minimum(np.minimum(r, g), b) >= 24) & (high <= 235)
    # Cyan and blue icons are no bar colour.
    bar &= ~((b > r + 15) & (b > g - 20))
    # Green, red, and the pale yellow fill and orange lost part of a hit.
    bar &= (g - np.maximum(r, b) > 12) | reddish | (np.minimum(r, g) - b > 25)
    # A red or yellow blip at the map's lower edge sits on the bar and reaches above it; the
    # orange and pale yellow a hit paints stay inside the bar.
    ar, ag, ab = track[:4].transpose(2, 0, 1)
    blip = ((ar - np.maximum(ag, ab) > 100) | ((np.minimum(ar, ag) - ab > 100) & (ag > 150))).any(axis=0)
    # A red bar is red wherever it is bar coloured. On a green one, red is the bright orange of a
    # hit's lost part (red 125 and up) or an icon: a small dark red cross or star over the bar is
    # no bar colour.
    candidates = (bar.sum(axis=0) >= 3) & ~blip
    if candidates.sum() < HEALTH_COLUMNS // 2:
        return False, None, False
    channel = 0 if (reddish.sum(axis=0)[candidates] >= 3).mean() >= 0.85 else 1
    if channel == 1:
        bar &= ~reddish | (r >= HEALTH_ORANGE)
    # An icon's anti-aliased rim is a blend of its colour and the bar's that can pass for either:
    # leave two columns more out on each side.
    invalid = np.pad((bar.sum(axis=0) < 3) | blip, 2)
    valid = ~(invalid[:-4] | invalid[1:-3] | invalid[2:-2] | invalid[3:-1] | invalid[4:])
    columns = np.flatnonzero(valid)
    if len(columns) < HEALTH_COLUMNS // 2:
        return False, None, False
    red = reddish.sum(axis=0)[columns] >= 3
    if channel == 1 and red[0]:
        # A green bar starts with its fill: red before it is an enemy's blip at the map's corner.
        columns = columns[np.argmin(red) :]
        if len(columns) < HEALTH_COLUMNS // 2:
            return True, None, False
    # The second brightest of the four rows: an icon's dark rim across one or two rows of the fill
    # does not make it look empty, and one bright row of a damaged frame does not make it fill.
    values = np.sort(pixels[:, columns, channel], axis=0)[2].astype(np.float64)
    n = len(values)
    total, squares = np.cumsum(values), np.cumsum(values * values)
    # Every split into a brighter fill on the left and a darker rest on the right, at least three
    # columns of each; the best one by squared error.
    split = np.arange(3, n - 2)
    fill = total[split - 1] / split
    rest = total[-1] - total[split - 1]
    empty = rest / (n - split)
    best = int((squares[-1] - total[split - 1] * fill - rest * empty).argmin())
    split, fill, empty = int(split[best]), float(fill[best]), float(empty[best])
    step = fill - empty
    if step >= HEALTH_STEP and empty <= fill * HEALTH_EMPTY:
        if fill < HEALTH_FILL[channel]:
            # The fill itself is dim: a green one while the picture fades in, a red one as it
            # pulses at low health.
            return True, None, channel == 1
        threshold = (fill + empty) / 2
        # Fill columns darker than halfway are wrong, and so are columns beyond the end almost as
        # bright as the fill; a background that lightens towards the far right of the empty track
        # is not.
        wrong = (values[:split] < threshold).sum() + (values[split:] >= fill - step / 4).sum()
        # Beyond the one column on either side of the end that may be a blend of both, two columns
        # are clearly fill and two clearly not, and the end is sharp: a lighter background behind
        # the translucent track fades, the bar stops. A Wi-Fi frame blurs an end over four columns.
        fill_side = values[split - 3 : split - 1] >= threshold
        empty_side = values[split + 1 : split + 3] < threshold
        clean = fill_side.all() and empty_side.all()
        drop = values[max(split - HEALTH_SHARP[0], 0)] - values[min(split + HEALTH_SHARP[1], n - 1)]
        sharp = drop >= step * 0.6
        # The end lies between the last fill column and the first darker one that could be read.
        before, after = int(columns[split - 1]) + 1, int(columns[split])
        if wrong > max(2, n * 0.12) or not clean or not sharp or after - before > HEALTH_HIDDEN:
            return True, None, False
        # The bar is drawn alike in its four rows, and so is the track behind it; around an end
        # that is an icon's dark rim on a light face they differ.
        near = high[:, columns[max(split - 3, 0) : split + 3]]
        if (near.max(axis=0) - near.min(axis=0) > HEALTH_UNEVEN).any():
            return True, None, False
        # A few fill-like columns just beyond an icon are its glow as often as the bar: the fill
        # that ends here has to run for a while unbroken, or start at the track's start.
        start = split - 1
        while start > 0 and columns[start] - columns[start - 1] == 1:
            start -= 1
        if columns[start] > 0 and split - start < HEALTH_RUN:
            return True, None, False
        return True, (before + after) / 2 / HEALTH_TRACK, False
    # No step: the whole track is one level. Full when that level is a bright green fill that
    # reaches the track's end; a red track is never full, and a dim one says nothing. The first
    # four columns are left out: the track's first column is a little darker, and a blip's rim at
    # its start is olive.
    level = np.sort(values[4:])
    if channel == 0 or float(level[0]) < HEALTH_FILL[1] or float(level[-1] - level[0]) > HEALTH_FLAT:
        return True, None, channel == 1 and float(level[-1]) < HEALTH_FILL[1]
    # The last few columns can be the empty part of a bar at 0.95 lit by sand behind it, or the
    # lost part of a small hit fading from orange: as bright as the fill, but darker or less green
    # than the rest of the track.
    tint = np.sort(g - r, axis=0)[2]
    if (
        values[-4:].mean() < np.median(values) - HEALTH_FLAT / 3
        or tint[-4:].mean() < np.median(tint[columns]) - HEALTH_TINT
    ):
        return True, None, False
    if HEALTH_COLUMNS - 1 - int(columns[-1]) > HEALTH_HIDDEN:
        return True, None, False
    return True, HEALTH_COLUMNS / HEALTH_TRACK, False


# The health track is x 64 to 152; x 153 is its dark border, which the old reader counted in, so a
# full bar reads 89 / 90 as it always has.
HEALTH_COLUMNS = 89
HEALTH_TRACK = 90
# Fill and empty differ by at least this much in their own channel. Measured on the cable
# recordings: a green fill at 164 to 216 against an empty track at 45 to 132, also in front of
# bright sand.
HEALTH_STEP = 30
# A fill dimmer than this is a picture fading in from black (green 87 to 193 over 0.4 s in enemy-13)
# or a red bar pulsing at low health.
HEALTH_FILL = (150, 140)
# The empty part is at most this share of the fill: a darker background behind part of the fill
# makes a step of a tenth or so, not more.
HEALTH_EMPTY = 0.85
HEALTH_FLAT = 30
HEALTH_RUN = 6
HEALTH_SHARP = (3, 2)
# Red on a green bar below this is an icon's: the orange lost part of the 47 hits in lab/health/
# has red 125 or more in 99 of 100 pixels, a dark red cross on the bar about 90.
HEALTH_ORANGE = 120
# Across its four rows a column of the bar or the track varies by 3 to 11 in nine of ten frames;
# under an icon's rim by a hundred and more.
HEALTH_UNEVEN = 60
# Green minus red of the last four columns of a full bar is 11 to 15 below the track's median where
# the blue of the armour track bleeds into them; under the fading lost part of a small hit 30 below.
HEALTH_TINT = 20
# Up to four columns of an end hidden under an icon's rim are read as their middle (0.02 either way).
HEALTH_HIDDEN = 4


def _bars(frame: np.ndarray) -> tuple[float | None, float | None, float | None]:
    # The track remains coloured even when empty. Chroma locates the HUD;
    # brightness relative to its translucent surround measures the filled part.
    band = frame[676:680, 64:244].astype(np.float32).mean(axis=0)
    surround = frame[[672, 682], 64:244].astype(np.float32).mean(axis=0)
    r, g, b = band.T
    sr, sg, sb = surround.T
    blue = (b - r > 8) & (b - r - (sb - sr) > 8)
    yellow = (np.minimum(r, g) - b > 35) & (np.minimum(r, g) - b - (np.minimum(sr, sg) - sb) > 20)
    health_visible, health, dim = _health(frame[670:680, 64 : 64 + HEALTH_COLUMNS].astype(np.int16))
    # All three differently coloured tracks establish the fixed geometry. This
    # prevents scene foliage or a billboard from being read as a health bar.
    armour_visible = blue[94:136].mean() > 0.7
    special_visible = yellow[138:180].mean() > 0.7
    # While the HUD fades in, the armour and special tracks read empty too: nothing is read.
    if dim or sum((health_visible, armour_visible, special_visible)) < 2:
        return None, None, None
    corrected = band - 0.25 * surround
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
        if screen in ("loading", "failed", "pause", "map", "wasted", "interaction_menu"):
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

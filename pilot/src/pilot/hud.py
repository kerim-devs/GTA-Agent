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

PAUSE_TITLE_UI = _template(
    (28, 178),
    b"c-rMyS#KOg5N-%Z2;_p?K|%x&As`;Y142l^144i}LXx!|=dc`p9uNougc2bH2_kWXxD7%{h+_xa@!IR%Ir^@qs(NO3#`X#$MdE>d"
    b"nBD1_?*6*^`@X7PA^sO1>sDy=uFu<JKG<73zm`&I{ck$xE&`)11ORIAvfuhb2ts^RZ=7}6`>UQXyHNyXz8H}Zt9<o{jaEJI#(585"
    b"gy=T{bedxC-2&=y4$jUkdv(EeRvdy>jGxcEiGXb`4pN|3jo5qjZujPjvJrpYXMoJy*x8%4_<Th>v+UJ&r`=~$`D-!AZS?KjU;Aot"
    b"`^S%iDu+@(`7p<_&j2n6My$kry~YWc3(JYvaW}TD7~}j8ejFw?Ma1WyM#M$LR~O@|$Z|XREVr6|GX09aq(5C70(r4~JNm5pnhsm&"
    b"vH#?@LgO!E;Js#sNQ}0oWoTXOh4S=MM?APN@W|ZimYJzT{GQ9_b6Y&}-WtPQj7{d#5RCL;@p5mOUZjx~FhSR!13t^cf||QYx2-Hs"
    b"7kg8jav=^?btR)xinp~^%Q-}u`&32~%OSM2Q-&rm#-@wX)DhdMVGg1TnL?zzZypx4cAmSKj$UYk@lcTp>hP);Yj{eYB;dO<ZJn|W"
    b"8MzP^gZ-wrC9G;!@W_`UK1SW0ksMbq8W<=X#wsVput*&uw%X3%Z(T!d3dGu^;<#vW0KA(%Ixz0@l$y=WsQ0Tv+|xy@_I&Hl-z~&@"
    b"z+lo~kfLos``Rt0v=ons`3lhk?}yEv6-)W&5Zya35#q~F(VZok*$a;dkpLo5=weUOQ(L3tjUmF|%-0X$)Z}6TQ^x)y!b2;1$gZfo"
    b"^%e5BHVB`tBg7o|EZB|2<7^Kv?$Y|YyYSDCO}1khV(mJQ$F>ijC(U@0I?j%J4(7OkxNKWP?A$aX#&Mp*)daLu9aZINl_JUFq*ZG;"
    b"udi)DlpO5>vD-i$;88-6ird+edbsG-pY`mzIx7f^o_>Z=T<5_Y97DuWKwdWlL@j$~YKUhBxRIZkU|$n5n3FuEMZP4Fy-;ORV#T^b"
    b"KwZT5(S!?+aYW)8dp#Cl{x%fMseKWp5pQBRt!As9e4%2y4v@^TC_qUKAYvVLRaqq7%npcxLX?vILEOYV_R%MhC(*HdsHv5=pocgG"
    b"e=n^%f0&0_iuemcmst)yBYtBN6=yicldpFb1=hk~85~sM0M21nK&)>L^7?$t7Z_J*;o5a$d6iDPYThb%*+U$+Fm--Ci8$ZR89eSv"
    b"#jpvzEN4Z;Z=t{Qz)oL3P?)(#pEEF24(x#um+`J4o*U*E#`l6bf-y$ZPBr-K1p1g?&LjqtvAxADOl-P|l9Afj2XUax*F(%&bE7!D"
    b"nQRn|az-fShdDhl+kJyz$JwjY_h$Y`7ctdw!vcNzhcn;(_{%S6PU7^g>~px=NmARiPf%@bew=jdW{k8^+q)KBtDOijgiXbiQBBsJ"
    b"WW)n(KH6V6Iii#sDl-f^b)y?&TSKfEG4N^t<3GeEvHwUJ&X`l2KRsCXxhOFuV&*j4s9&ro^j3<r-O8Ca_B3@?WX;0PO;m}Cte6;N"
    b"e}~Jj9!BahVp||S98(I<US)-Bavy#V*?@>KOZEuh3+}_GL)}$ckeN>yY;@gLpy(zRHdT~YVg8>|jKkR4LbthiWeH-`tay<UEFp#>"
    b"Mu^z;LEMNLBqH{R*yVBEArTNmg+;U|5r67oeBTpAcrC}csq)QaAz@w5-Ks}~b6GPF;?8)ZT4N1SgwM%|0cN9&WF{V$GuneCkL!q?"
    b"Y#y#6##N&1NLZ5WyJQl$b7hw)CAp;F>I%4smoi&V)kP>Mz!gVTtLb#JD@0@FnC6a;BNL4-C#^N;R3>_GM6BJ9Tx`}5>)As*fR5yH"
    b"M>(J<Bdb7^elCJc$}Xy?OL*I(y8&eA$5#y_Zo_m;TGc`n{daFkDsWdaKqWBZ>zoZbKBXM(EX^L3>CGV|4RkIw>6BD0EA(uPvE-|B"
    b"$LVCJe#^n>u>)Pi0G-U0U7E2ezpw@`h<hq?*=COV!k0qa4B-RB*fG0%)1X#cJG(I^xmYF-A|8x73zEuWcMSJgMFH6ctqyAn+<^*W"
    b"v@=AkLxC7qK0-kVO5w00Z<9fP9utx&#qV4zerv4i=7Y(S6s5R}ZJE6|Eb4R~UH7i4y+LPVcayYDaK~o3O1^j^W>HXBQFl57l}l?#"
    b"o1?6FugAa7TNT7U8OII)w#oR_+$bIz@ja6+j_xN`%yu23I1<Y=jRl;Z!AkH~Fl}-6r&AHn*j2io4Ox0l?5LhYe*Z>1P`y9V7+HE$"
    b"8Lpp*dp}1<RyaErdC;dZVRGYfVvAqJF>LD{YsK~@Z4Yj_cS+0rxAZ>`<5=0bO%xS3c#tVJ^FRC_2x4)-f=@)!vkFY;ctuv&49&&n"
    b"kf%y(rF7bnUYc7D<Zr2GNap",
)

PAUSE_TITLE_UI_MASK = _template(
    (28, 178),
    b"c-rNd+mZtz2t?`s|LLvNB+_8xh?Cuyol4bQL^&!T#Oz;O!0yMZp=>(V-yD;q@wsk^@n9MsQNK5ld&IBC>vv0BQM^Bc?y%mJNf<uP"
    b"QaU!{kQlUSJz~LM6C3<?M~sESzaxg~WUV!RZ`05;h%cK%@J66|v1zZ8T(I<HOBReNDNQ;8Y3MSXkTtM6Y!a(3f*1v{5*H!E;BzBy"
    b"MDeVMM_ULX%#>nGGSRoptR)&&UVc~O6ZdCBVaJo4(`(N&NemfXf*EJxY085Vl@rmnWDE{XxeuaIGO-;H)41wc6O$YWLlN7W*fOz?"
    b"I(o-xxWnENLlfH_u{DXwu107`#PRg)5`)6db7Bi=fL`OAFFYlNB*rOm?h*{AMT`}(^rQ|kYGUAUjh&J<YdXb>;oHP1wmw^9mBpwW"
    b"b)T3mHslpCwmu;)ts*S%E-?+jr={?sV`6m-(}8E2*yIT^_m{*n9wTS5o5VJ0ToFT_l8{E_H)vu2C$WN6=71Cifh`xNAT}ADAhS(k"
    b"tcXz)$G8zazb;zf#cmp2CRc*kN@BJKy~cCSkR2@)U#ofr)tf49atcLux><%HX_|??`=`fbhxiRGO(tH+R7}Lu2)a=E*7XA*rUxq",
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

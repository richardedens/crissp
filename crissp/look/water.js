/* The water under the framework's pages: a still-moving shader on plain WebGL (adapted from the water background of
   an earlier product's design system; it loads nothing). Dark as drawn, a pale surface under data-theme=light,
   following the page's theme switch; a click sends a ripple, opening a <details> a stronger one; one still frame under
   reduced motion. Used by the Tests dashboard and the UX suite, and built into the Claude session pages
   (crissp/testsuite/lib/sessionview.py). */
(()=>{let c=document.querySelector('.water canvas');if(!c){const w=document.createElement('div');w.className='water';
w.setAttribute('aria-hidden','true');w.innerHTML='<canvas></canvas><i></i>';document.body.prepend(w);c=w.firstChild;}
const gl=c&&c.getContext('webgl',{antialias:false,depth:false});
if(!gl)return;const root=document.documentElement,still=matchMedia('(prefers-reduced-motion: reduce)');
const FRAG=`precision highp float;uniform vec2 uRes;uniform float uT;uniform vec4 uRip[12];uniform int uN;uniform vec3 uFloor;
uniform vec3 uPoolA;uniform vec3 uPoolB;uniform vec3 uCaus;uniform vec3 uGlint;uniform float uLight;
float surface(vec2 p){float t=uT*.22;return sin(p.x*4.2+t+sin(p.y*3.1-t*.7))*.075+sin(p.y*6.3-t*.85+p.x*2.1)*.038
+sin(p.x*9.4+p.y*7.2+t*1.2)*.012;}
float ripple(vec2 p){float h=0.;for(int i=0;i<12;i++){if(i>=uN)break;float age=uT-uRip[i].z;if(age<=0.||age>8.)continue;
float d=distance(p,uRip[i].xy);float w=d-age*.23;h+=sin(w*48.)*exp(-w*w/(.016+age*.018))*exp(-age*.9)*uRip[i].w*.016;}return h;}
float caustic(vec2 p){float t=uT*.09;p+=vec2(sin(p.y*1.3+t),cos(p.x*1.1-t))*.7;float a=sin(p.x*3.+sin(p.y*2.+t)+t);
float b=sin(p.y*3.5+cos(p.x*2.4-t)-t*.7);return pow(max(0.,1.-abs(a+b)*.6),12.);}
void main(){vec2 uv=gl_FragCoord.xy/uRes;vec2 p=(uv-.5)*vec2(uRes.x/uRes.y,1.);float e=.003;float h=surface(p)+ripple(p);
vec2 slope=(vec2(surface(p+vec2(e,0.))+ripple(p+vec2(e,0.)),surface(p+vec2(0.,e))+ripple(p+vec2(0.,e)))-h)/e;
vec2 r=p+slope*.16;float lagoon=exp(-dot(r-vec2(.55,-.16),r-vec2(.55,-.16))*1.8);
float blue=exp(-dot(p-vec2(-.65,.35),p-vec2(-.65,.35))*2.);vec3 pools=uPoolA*lagoon+uPoolB*blue;
vec3 color=uLight>.5?uFloor-pools:uFloor+pools;float l=caustic(r*2.4)*.65+caustic(r*3.1+2.8)*.35;
color+=uCaus*l*(.10+lagoon*.22);vec3 n=normalize(vec3(-slope*.5,1.));
color+=uGlint*pow(max(dot(n,normalize(vec3(-.3,.4,1.))),0.),38.)*.08;
color*=1.-(uLight>.5?.06:.28)*smoothstep(.2,.95,length(uv-.5));gl_FragColor=vec4(color,1.);}`;
const sh=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);return s;};
const p=gl.createProgram();gl.attachShader(p,sh(gl.VERTEX_SHADER,'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}'));
gl.attachShader(p,sh(gl.FRAGMENT_SHADER,FRAG));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))return;
gl.useProgram(p);gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
const at=gl.getAttribLocation(p,'a');gl.enableVertexAttribArray(at);gl.vertexAttribPointer(at,2,gl.FLOAT,false,0,0);
const U=n=>gl.getUniformLocation(p,n);
const DARK=[[.020,.024,.040],[.02,.12,.14],[.11,.05,.22],[.22,.46,.58],[.52,.30,.66],0];
const LIGHT=[[.955,.962,.978],[.21,.07,.09],[.10,.17,.02],[.07,.09,.10],[.18,.16,.22],1];
const tint=()=>{const t=root.dataset.theme==='light'?LIGHT:DARK;['uFloor','uPoolA','uPoolB','uCaus','uGlint'].forEach((u,i)=>gl.uniform3fv(U(u),t[i]));
gl.uniform1f(U('uLight'),t[5]);};
const rip=new Float32Array(48);let count=0,next=0,last=0;const t0=performance.now(),now=()=>(performance.now()-t0)/1000;
const ripple=(x,y,amp)=>{if(still.matches)return;const w=c.clientWidth,h=Math.max(1,c.clientHeight);
rip.set([(x/w-.5)*w/h,.5-y/h,now(),amp],next*4);next=(next+1)%12;count=Math.min(12,count+1);};
const draw=()=>{gl.uniform1f(U('uT'),still.matches?7.3:now());gl.uniform4fv(U('uRip'),rip);gl.uniform1i(U('uN'),count);
gl.drawArrays(gl.TRIANGLE_STRIP,0,4);};
const resize=()=>{const k=Math.min(devicePixelRatio||1,1.5)*(c.clientWidth<820?.5:.65);
c.width=Math.max(2,Math.round(c.clientWidth*k));c.height=Math.max(2,Math.round(c.clientHeight*k));
gl.viewport(0,0,c.width,c.height);gl.uniform2f(U('uRes'),c.width,c.height);draw();};
const tick=t=>{requestAnimationFrame(tick);if(document.hidden||still.matches||t-last<33)return;last=t;draw();};
addEventListener('resize',resize);new MutationObserver(()=>{tint();draw();}).observe(root,{attributes:true,attributeFilter:['data-theme']});
addEventListener('pointerdown',e=>ripple(e.clientX,e.clientY,.35));
document.addEventListener('toggle',e=>{const r=e.target.getBoundingClientRect();ripple(r.left+r.width/2,r.top+16,.9);},true);
tint();resize();requestAnimationFrame(tick);})();

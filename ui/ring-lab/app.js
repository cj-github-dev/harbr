
const defaults={
  breathAmp:2.8,breathPeriod:7.2,lightPeriod:31,auraRadius:80,auraIntensity:.46,
  ripplePeriod:9.2,rippleOpacity:.40,rippleScale:1.85,buoyancyAmount:3,buoyancyPeriod:13.8,bloom:.55
};
const presets={
  subtle:{breathAmp:1.2,breathPeriod:8.6,lightPeriod:36,auraRadius:55,auraIntensity:.25,ripplePeriod:11.5,rippleOpacity:.22,rippleScale:1.65,buoyancyAmount:1.5,buoyancyPeriod:16,bloom:.32},
  balanced:defaults,
  pronounced:{breathAmp:3.8,breathPeriod:6.4,lightPeriod:24,auraRadius:105,auraIntensity:.62,ripplePeriod:7.4,rippleOpacity:.58,rippleScale:2.05,buoyancyAmount:5,buoyancyPeriod:11.8,bloom:.72},
  dramatic:{breathAmp:5.4,breathPeriod:5.4,lightPeriod:15,auraRadius:140,auraIntensity:.86,ripplePeriod:5.5,rippleOpacity:.82,rippleScale:2.35,buoyancyAmount:9,buoyancyPeriod:8.2,bloom:1}
};
const units={breathAmp:"%",breathPeriod:" s",lightPeriod:" s",auraRadius:" px",auraIntensity:"",ripplePeriod:" s",rippleOpacity:"",rippleScale:"×",buoyancyAmount:" px",buoyancyPeriod:" s",bloom:""};
const css={breathAmp:"--breath-amp",breathPeriod:"--breath-period",lightPeriod:"--light-period",auraRadius:"--aura-radius",auraIntensity:"--aura-intensity",ripplePeriod:"--ripple-period",rippleOpacity:"--ripple-opacity",rippleScale:"--ripple-scale",buoyancyAmount:"--buoyancy-amount",buoyancyPeriod:"--buoyancy-period",bloom:"--bloom"};
function apply(values){
  Object.entries(values).forEach(([id,val])=>{
    const input=document.getElementById(id); input.value=val;
    const out=document.getElementById(id+"Out"); out.value=`${val}${units[id]}`;
    let v=val;
    if(["breathAmp"].includes(id))v=`${val}%`;
    if(["breathPeriod","lightPeriod","ripplePeriod","buoyancyPeriod"].includes(id))v=`${val}s`;
    if(["auraRadius","buoyancyAmount"].includes(id))v=`${val}px`;
    document.documentElement.style.setProperty(css[id],v);
  });
}
Object.keys(defaults).forEach(id=>document.getElementById(id).addEventListener("input",e=>apply({[id]:Number(e.target.value)})));
document.querySelectorAll("[data-preset]").forEach(btn=>btn.addEventListener("click",()=>{
  document.querySelectorAll("[data-preset]").forEach(b=>b.classList.remove("active"));
  btn.classList.add("active"); apply(presets[btn.dataset.preset]);
}));
document.getElementById("reset").addEventListener("click",()=>apply(defaults));
document.getElementById("toggle-controls").addEventListener("click",e=>{
  document.body.classList.toggle("controls-hidden");
  e.target.textContent=document.body.classList.contains("controls-hidden")?"Show controls":"Hide controls";
});
apply(defaults);

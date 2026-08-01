/* ===========================================================
   FoodieNepal — shared front-end behaviour
   =========================================================== */
(function(){

/* ---------- toast ---------- */
function toast(msg, kind){
  const stack=document.getElementById("toastStack");
  if(!stack) return;
  const el=document.createElement("div");
  el.className="toast";
  if(kind==="error") el.style.borderLeftColor="var(--accent-3)";
  if(kind==="success") el.style.borderLeftColor="var(--success)";
  el.textContent=msg;
  stack.appendChild(el);
  setTimeout(()=>{ el.classList.add("hide"); setTimeout(()=>el.remove(),320); },3800);
}
window.foodieToast=toast;

if(window.__flashes && window.__flashes.length){
  window.__flashes.forEach((m,i)=>setTimeout(()=>toast(m),200*i));
}

/* ---------- header scroll shadow ---------- */
const header=document.getElementById("siteHeader");
if(header){
  window.addEventListener("scroll",()=>{
    header.classList.toggle("scrolled", window.scrollY>8);
  },{passive:true});
}

/* ---------- mobile nav toggle ---------- */
const navToggle=document.getElementById("navToggle");
const mainNav=document.getElementById("mainNav");
if(navToggle && mainNav){
  navToggle.addEventListener("click",()=>mainNav.classList.toggle("open"));
}

/* ---------- notification bell ---------- */
const bellBtn=document.getElementById("bellBtn");
const notifPanel=document.getElementById("notifPanel");
const notifList=document.getElementById("notifList");
const markAllRead=document.getElementById("markAllRead");

function renderNotifs(items){
  if(!notifList) return;
  if(!items.length){ notifList.innerHTML='<div class="notif-empty">🎉 You are all caught up</div>'; return; }
  notifList.innerHTML=items.map(n=>`
    <div class="notif-item ${n.read?'':'unread'}" data-id="${n.id}">
      <div class="t"><span>${n.title||''}</span><span style="color:var(--text-faint);font-weight:400">${n.time||''}</span></div>
      <div class="m">${n.message||''}</div>
    </div>`).join("");
}

async function loadNotifs(){
  if(!notifList) return;
  try{
    const r=await fetch("/api/notifications/recent");
    if(!r.ok) return;
    const data=await r.json();
    renderNotifs(data);
  }catch(e){}
}

async function pollCount(){
  if(!bellBtn) return;
  try{
    const r=await fetch("/api/notifications/count");
    if(!r.ok) return;
    const d=await r.json();
    let badge=document.getElementById("notifBadge");
    if(d.count>0){
      if(!badge){
        badge=document.createElement("span");
        badge.id="notifBadge"; badge.className="badge pulse";
        bellBtn.appendChild(badge);
      }
      if(badge.textContent!=String(d.count)){ badge.textContent=d.count; badge.classList.add("bump"); setTimeout(()=>badge.classList.remove("bump"),450); }
    } else if(badge){ badge.remove(); }
  }catch(e){}
}

if(bellBtn){
  bellBtn.addEventListener("click",(e)=>{
    e.stopPropagation();
    notifPanel.classList.toggle("open");
    if(notifPanel.classList.contains("open")) loadNotifs();
  });
  document.addEventListener("click",(e)=>{
    if(notifPanel && !notifPanel.contains(e.target) && e.target!==bellBtn) notifPanel.classList.remove("open");
  });
  setInterval(pollCount, 15000);
}
if(markAllRead){
  markAllRead.addEventListener("click", async ()=>{
    await fetch("/notifications/read_all?ajax=1",{method:"POST"});
    loadNotifs();
    const b=document.getElementById("notifBadge"); if(b) b.remove();
    toast("All notifications marked as read","success");
  });
}

/* ---------- button loading state on submit ---------- */
document.querySelectorAll("form").forEach(f=>{
  f.addEventListener("submit",()=>{
    const btn=f.querySelector('button[type="submit"], .btn[type="submit"], form button');
    if(btn && !btn.classList.contains("loading")){
      btn.classList.add("loading");
      btn.dataset.orig=btn.innerHTML;
      btn.innerHTML='<span class="spinner"></span><span class="label">Please wait…</span>';
    }
  });
});

/* ---------- geolocation helper (home + checkout) ---------- */
window.foodieLocate=function(latId,lngId,onDone){
  if(!navigator.geolocation){ toast("Location is not available in this browser.","error"); return; }
  navigator.geolocation.getCurrentPosition(
    p=>{
      const lat=p.coords.latitude, lng=p.coords.longitude;
      if(latId) document.getElementById(latId).value=lat;
      if(lngId) document.getElementById(lngId).value=lng;
      toast("Location detected","success");
      if(onDone) onDone(lat,lng);
    },
    ()=>toast("Location permission was denied.","error")
  );
};

/* ---------- home map ---------- */
window.foodieHomeMap=function(){
  const el=document.getElementById("map");
  if(!el || typeof L==="undefined") return;
  const map=L.map(el).setView([28.3949,84.1240],7);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap"}).addTo(map);
  fetch("/api/restaurants").then(r=>r.json()).then(rs=>{
    const bounds=[];
    rs.forEach(x=>{
      if(x.lat && x.lng){
        L.marker([x.lat,x.lng]).addTo(map)
          .bindPopup(`<b>${x.name}</b><br>${x.city||''}, ${x.province||''}<br><a href="${x.url}">View menu →</a>`);
        bounds.push([x.lat,x.lng]);
      }
    });
    if(bounds.length) map.fitBounds(bounds,{padding:[30,30]});
  });
};

/* ---------- animated counters (admin/dashboard stats) ---------- */
window.foodieCountUp=function(){
  document.querySelectorAll("[data-count]").forEach(el=>{
    const target=parseFloat(el.getAttribute("data-count"))||0;
    const dur=700; const start=performance.now();
    function step(t){
      const p=Math.min(1,(t-start)/dur);
      const val=Math.floor(p*target);
      el.textContent=(el.getAttribute("data-prefix")||"")+val+(el.getAttribute("data-suffix")||"");
      if(p<1) requestAnimationFrame(step); else el.textContent=(el.getAttribute("data-prefix")||"")+target+(el.getAttribute("data-suffix")||"");
    }
    requestAnimationFrame(step);
  });
};
document.addEventListener("DOMContentLoaded",window.foodieCountUp);

/* ---------- star rating input ---------- */
window.foodieStarInput=function(containerId, inputId, initial){
  const box=document.getElementById(containerId);
  const input=document.getElementById(inputId);
  if(!box||!input) return;
  const stars=[1,2,3,4,5];
  function draw(v){
    box.innerHTML=stars.map(i=>`<span class="s ${i<=v?'on':''}" data-v="${i}">★</span>`).join("");
  }
  let val=initial||0;
  draw(val);
  box.addEventListener("click",e=>{
    if(e.target.dataset.v){ val=parseInt(e.target.dataset.v); input.value=val; draw(val); }
  });
  box.addEventListener("mouseover",e=>{
    if(e.target.dataset.v) draw(parseInt(e.target.dataset.v));
  });
  box.addEventListener("mouseleave",()=>draw(val));
};

/* ---------- cart quantity stepper (AJAX) ---------- */
window.foodieCartStep=async function(fid, delta, min){
  const span=document.getElementById("qty-"+fid);
  if(!span) return;
  let qty=parseInt(span.textContent)+delta;
  if(qty<(min||0)) qty=(min||0);
  try{
    const r=await fetch("/api/cart/set",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({fid:fid,qty:qty})});
    const data=await r.json();
    if(data.error){ toast(data.error,"error"); return; }
    if(qty<=0){
      const row=document.getElementById("row-"+fid);
      if(row){ row.classList.add("removing"); setTimeout(()=>{row.remove(); foodieUpdateCartTotals(data);},280); }
    } else {
      span.textContent=qty; span.classList.add("bump"); setTimeout(()=>span.classList.remove("bump"),300);
      foodieUpdateCartTotals(data);
    }
  }catch(e){ toast("Could not update cart","error"); }
};

window.foodieUpdateCartTotals=function(data){
  const totalEl=document.getElementById("cartTotal");
  const subEl=document.getElementById("cartSubtotal");
  if(totalEl) totalEl.textContent="Rs. "+data.total.toFixed(2);
  if(subEl) subEl.textContent="Rs. "+data.total.toFixed(2);
  const cartBadge=document.getElementById("cartBadge");
  if(cartBadge){
    if(data.count>0){ cartBadge.textContent=data.count; cartBadge.classList.add("bump"); setTimeout(()=>cartBadge.classList.remove("bump"),400); }
    else cartBadge.remove();
  }
  if(data.items && data.items.length===0){
    const list=document.getElementById("cartList");
    if(list) list.innerHTML='<div class="empty-state"><span class="big">🛒</span>Your cart is empty.<br><a class="btn" style="margin-top:14px;display:inline-block" href="/">Browse restaurants</a></div>';
    const summary=document.getElementById("cartSummaryBox");
    if(summary) summary.style.display="none";
  }
};

})();

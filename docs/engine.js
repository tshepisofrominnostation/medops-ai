/* MedOps AI — client-side port of the Smart Classification Engine.
   Parity-tested against the Python backend (app/classifier.py, prioritizer.py). */

const CATEGORY_KEYWORDS = {
  "IT & Medical Tech": {
    network:3, server:3, terminal:3, telemetry:3, monitoring:2, monitor:2,
    disconnect:2, wifi:3, software:2, login:2, emr:3, database:3, computer:2,
    system:1, connectivity:2, synch:1, sync:1, reboot:2, crash:2, offline:2,
    workstation:2, ventilator:3, defibrillator:3, "infusion pump":3, dialysis:3,
    "crash cart":3, "x-ray":3, scanner:2, eeg:3, ecg:3
  },
  "HR": {
    leave:3, shift:2, contract:2, recruitment:3, hiring:3, onboarding:2,
    staffing:2, roster:2, sabbatical:2, grievance:2, disciplinary:2, training:1,
    resignation:3, payroll:2, hr:3, overtime:2, personnel:2
  },
  "Finance": {
    invoice:3, billing:3, payment:3, claim:3, budget:3, purchase:2,
    reimbursement:3, tender:2, expense:2, accounts:2, debtors:3,
    "medical aid":3, tariff:2, finance:3
  },
  "Operations": {
    light:2, aircon:3, "air conditioning":3, water:2, leak:3, generator:3,
    door:1, elevator:2, lift:2, cleaning:2, plumbing:3, maintenance:3,
    ceiling:2, paint:2, refuse:2, "bed ":1, garden:2, kitchen:2
  }
};
const DEFAULT_CATEGORY = "Operations";
const CLINICAL_CONTEXT = ["emergency","icu","intensive care","theatre","operating room","telemetry","patient monitor","patient bay","ward","bay "];
const CLINICAL_EQUIPMENT = ["ventilator","defibrillator","patient monitor","monitoring terminal","telemetry","infusion pump","dialysis","crash cart","life support"];
const SAFETY = ["fire","flood","gas leak","power failure","outage","electrical hazard","spill"];
const URGENT = ["down","not working","fail","keeps disconnect","urgent","immediately","critical","alarm","no power","offline","will not start","stopped"];
const ROUTINE = ["invoice","query","leave request","schedule","booking","question","monthly","routine","annual","reminder","planning"];
const ASSIGN = {
  "IT & Medical Tech": {High:"IT & Biomedical Engineering on-call",Medium:"IT Service Desk",Low:"IT Service Desk"},
  "HR": {High:"HR Duty Officer",Medium:"HR Business Partner",Low:"HR Admin Team"},
  "Finance": {High:"Finance Duty Officer",Medium:"Finance Operations Team",Low:"Finance Operations Team"},
  "Operations": {High:"Operations Emergency Response",Medium:"Operations & Maintenance Team",Low:"Operations & Maintenance Team"}
};

function dequote(t){
  t = t.trim();
  if (t.startsWith('"')) t = t.slice(1);
  if (t.endsWith('"')) t = t.slice(0,-1);
  return t.replace('." ',' ').trim();
}
function parseSender(raw){
  const m = raw.match(/[-\u2014\u2013]\s*([A-Z][\w.\-\s]+?)\s*\((.+?)\)\s*$/);
  if (m) {
    const body = dequote(raw.replace(m[0],"").trim());
    return {body, sender: m[1].trim()+" ("+m[2].trim()+")"};
  }
  return {body: dequote(raw.trim()), sender: "Unspecified hospital staff"};
}
function classify(message){
  const text = message.toLowerCase();
  const scores = {};
  let total = 0;
  for (const [cat,kws] of Object.entries(CATEGORY_KEYWORDS)){
    let s = 0;
    for (const [kw,w] of Object.entries(kws)){
      let idx = 0, count = 0;
      const needle = kw.toLowerCase();
      while ((idx = text.indexOf(needle, idx)) !== -1){ count++; idx += needle.length; }
      if (count > 0) s += w * (1 + count - 1);
    }
    scores[cat] = s; total += s;
  }
  if (total === 0) return {category: DEFAULT_CATEGORY, confidence: 0};
  let best = DEFAULT_CATEGORY, bestScore = -1;
  for (const [cat,s] of Object.entries(scores)) if (s > bestScore){best=cat;bestScore=s;}
  return {category: best, confidence: Math.round(1000*bestScore/total)/1000};
}
function prioritize(message, sender){
  const text = (message+" "+sender).toLowerCase();
  let score = 0;
  const hit = arr => arr.some(k => text.includes(k));
  if (hit(CLINICAL_CONTEXT)) score += 3;
  if (hit(CLINICAL_EQUIPMENT)) score += 3;
  if (hit(SAFETY)) score += 4;
  if (hit(URGENT)) score += 2;
  if (hit(ROUTINE)) score -= 2;
  if (text.includes("high") || text.includes("emergency")) score += 1;
  return score >= 5 ? "High" : score >= 2 ? "Medium" : "Low";
}
function summarize(message, sender, category, priority){
  let core = message.trim().replace(/\.+$/,"");
  const words = core.split(/\s+/);
  if (words.length > 22) core = words.slice(0,22).join(" ")+"...";
  const dept = sender.includes("(") ? sender.split("(").pop().replace(")","") : "hospital staff";
  return core+". Reported by "+dept+"; classified as "+category+" with "+priority+" priority.";
}
function processTicket(raw, seq){
  const {body, sender} = parseSender(raw);
  const {category, confidence} = classify(body);
  const priority = prioritize(body, sender);
  return {
    ticket_id: "MED-"+String(seq).padStart(3,"0"),
    timestamp: new Date().toISOString().replace("Z","+00:00"),
    sender: sender, category: category, priority: priority,
    summary: summarize(body, sender, category, priority),
    assigned_to: ASSIGN[category][priority]
  };
}

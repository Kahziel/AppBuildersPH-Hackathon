const pinData = {
  1: { label: 'REFERENCE SUPPLY', color: '#f59e0b', wire: '703-OR-18', expected: '5.0 ± 0.2 VDC', function: '5 V reference supply' },
  2: { label: 'SENSOR SIGNAL', color: '#38bdf8', wire: '412-BU-18', expected: '0.5–4.5 VDC', function: 'Pressure signal return' },
  3: { label: 'GROUND CONTINUITY', color: '#a5b4c5', wire: '200-BK-14', expected: '≤ 5.0 Ω', function: 'Sensor ground continuity' },
};

export function renderWiring({ icon, selectedPin = 1 } = {}) {
  selectedPin = pinData[Number(selectedPin)] ? Number(selectedPin) : 1;
  const p = pinData[selectedPin] || pinData[1];
  const i = (name, size = 18) => icon ? icon(name, size) : '';
  return `<section class="wiring-screen screen-enter">
    <div class="wiring-page-heading"><div><div class="eyebrow">ELECTRICAL REFERENCE</div><h1>Follow the circuit.</h1><p class="muted">Every wire. Every pin. All on your device.</p></div><span class="badge badge-teal">${i('check',14)} DEMO SCHEMATIC</span></div>
    <div class="wiring-layout">
      <section class="panel wiring-canvas-panel">
        <div class="panel-header wiring-canvas-header"><div><span class="eyebrow">FUEL DELIVERY SYSTEM</span><h2>Pressure sensor circuit</h2></div><span class="wiring-page-code mono">EL–04 / 12</span></div>
        <div class="wiring-canvas" aria-label="Interactive fuel pressure sensor circuit diagram">
          <div class="wiring-canvas-caption"><span class="wiring-live-dot"></span> SELECT A PIN BELOW TO INSPECT</div>
          <svg class="wiring-circuit-svg" viewBox="0 0 760 390" role="img" aria-label="ECM connections to B41 fuel pressure sensor: orange 5 volt reference, blue signal, gray ground">
            <defs><pattern id="circuitDots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#303742"/></pattern><filter id="wireGlow"><feGaussianBlur stdDeviation="3"/></filter></defs>
            <rect width="760" height="390" fill="url(#circuitDots)"/>
            <g id="wiring-circuit-content">
              <text x="63" y="62" fill="#707c8d" font-size="11" font-family="Consolas,monospace" letter-spacing="2">ENGINE CONTROL MODULE</text>
              <rect x="58" y="82" width="138" height="214" rx="10" fill="#191e25" stroke="#46505d"/>
              <rect x="69" y="94" width="116" height="190" rx="5" fill="#14181e" stroke="#252d37"/>
              <text x="125" y="160" text-anchor="middle" fill="#d9e0e8" font-size="23" font-weight="700" font-family="Segoe UI,sans-serif">ECM</text>
              <text x="125" y="183" text-anchor="middle" fill="#7e8b9a" font-size="12" font-family="Consolas,monospace">J1 CONNECTOR</text>
              <path d="M98 211h54m-54 7h54m-54 7h54" stroke="#35404d" stroke-width="3"/>
              <text x="648" y="62" text-anchor="middle" fill="#707c8d" font-size="11" font-family="Consolas,monospace" letter-spacing="2">FUEL PRESSURE</text>
              <rect x="591" y="82" width="114" height="214" rx="10" fill="#191e25" stroke="#46505d"/>
              <rect x="605" y="102" width="86" height="72" rx="7" fill="#10151a" stroke="#303b47"/>
              <circle cx="648" cy="137" r="22" fill="none" stroke="#697889" stroke-width="2"/>
              <path d="M635 148l13-23 13 23" fill="none" stroke="#9ba7b5" stroke-width="2"/><circle cx="648" cy="139" r="3" fill="#9ba7b5"/>
              <text x="648" y="211" text-anchor="middle" fill="#e8edf3" font-size="25" font-family="Consolas,monospace" font-weight="700">B41</text>
              <text x="648" y="231" text-anchor="middle" fill="#7e8b9a" font-size="10" font-family="Consolas,monospace">PRESSURE SENSOR</text>
              <text x="648" y="266" text-anchor="middle" fill="#6e7c8e" font-size="10" font-family="Consolas,monospace">DT06–3S</text>
              ${[1,2,3].map((n) => { const y = 120 + (n-1)*68; const c = pinData[n].color; return `<g class="wiring-wire ${Number(selectedPin)===n?'is-active':''}"><path d="M196 ${y}H582" fill="none" stroke="${c}" stroke-width="${Number(selectedPin)===n?'4':'2'}" opacity="${Number(selectedPin)===n?'1':'.6'}"/><rect x="300" y="${y-25}" width="171" height="20" rx="3" fill="#10151b"/><text x="386" y="${y-11}" text-anchor="middle" fill="${c}" font-size="12" font-family="Consolas,monospace">${pinData[n].wire} · ${['5V','SIG','GND'][n-1]}</text><circle cx="196" cy="${y}" r="5" fill="#10151b" stroke="${c}" stroke-width="2"/><text x="216" y="${y+20}" fill="#778696" font-size="10" font-family="Consolas,monospace">J1–${[17,24,32][n-1]}</text><g class="wiring-pin-target" role="button" tabindex="0" aria-label="Inspect pin ${n}, ${pinData[n].function}" data-action="select-pin" data-pin="${n}"><rect x="544" y="${y-27}" width="53" height="54" rx="8" fill="transparent"/><circle cx="582" cy="${y}" r="${Number(selectedPin)===n?'13':'10'}" fill="#10151b" stroke="${c}" stroke-width="${Number(selectedPin)===n?'3':'2'}"/><text x="582" y="${y+4}" text-anchor="middle" fill="${c}" font-size="12" font-weight="700" font-family="Consolas,monospace">${n}</text></g></g>`; }).join('')}
              <path d="M438 256v44m-16 0h32m-26 6h20m-15 6h10" fill="none" stroke="#738396" stroke-width="2"/>
              <text x="59" y="345" fill="#526071" font-size="10" font-family="Consolas,monospace">HARNESS: ENG–FUEL–01</text>
              <text x="702" y="345" text-anchor="end" fill="#526071" font-size="10" font-family="Consolas,monospace">ILLUSTRATIVE CIRCUIT · VERIFY OEM SOURCE</text>
            </g>
          </svg>
        </div>
        <div class="wiring-canvas-toolbar"><div class="wiring-pin-controls" aria-label="Inspect circuit pin">${[1,2,3].map(n=>`<button class="wiring-pin-control ${selectedPin===n?'is-active':''}" style="--pin-color:${pinData[n].color}" data-action="select-pin" data-pin="${n}" aria-label="Inspect pin ${n}, ${pinData[n].function}" aria-pressed="${selectedPin===n}"><span class="mono">${n}</span>${['5V','SIGNAL','GROUND'][n-1]}</button>`).join('')}</div><div class="wiring-zoom-controls"><button class="wiring-square-button" data-action="zoom-out" aria-label="Zoom out">${i('minus',18)}</button><span class="mono" id="wiring-zoom-label" data-zoom-label>100%</span><button class="wiring-square-button" data-action="zoom-in" aria-label="Zoom in">${i('plus',18)}</button></div></div>
        <div class="wiring-canvas-footer"><span>${i('circuit',16)} 3 conductors <span class="wiring-footer-divider">/</span> 18–14 AWG</span><button class="wiring-text-button" data-action="open-source">View source ${i('arrow-up-right',16)}</button></div>
      </section>
      <section class="panel wiring-node-panel">
        <div class="wiring-node-top"><span class="wiring-component-symbol">${i('target',23)}</span><span class="badge badge-teal">LOCAL REFERENCE</span></div>
        <div class="eyebrow">SELECTED COMPONENT</div><h2>Fuel delivery<br>pressure sensor <span class="mono">B41</span></h2><p class="muted">Deutsch 3-Pin · DT06–3S</p>
        <div class="wiring-pin-focus" style="--pin-color:${p.color}"><div class="wiring-pin-number mono">${selectedPin}</div><div><div class="eyebrow">${p.label}</div><strong class="mono">${p.expected}</strong><span class="mono wiring-wire-id">${p.wire}</span></div></div>
        <div class="wiring-reading-note">${i('info',16)} <span>${selectedPin===3?'Key OFF · circuit isolated · pin 3 → ECM J1–32.':'Key ON · pin '+selectedPin+' → pin 3.'} Demo range; confirm the OEM test procedure.</span></div>
        <div class="wiring-pin-table"><div class="wiring-pin-table-head"><span>PIN</span><span>FUNCTION</span><span>EXPECTED</span></div>${[1,2,3].map(n=>`<button class="wiring-pin-row ${Number(selectedPin)===n?'selected':''}" data-action="select-pin" data-pin="${n}" aria-pressed="${Number(selectedPin)===n}"><span class="wiring-small-pin mono" style="--pin-color:${pinData[n].color}">${n}</span><span>${['5 V reference','Signal return','Ground continuity'][n-1]}</span><span class="mono">${['5.0 ± 0.2 V','0.5–4.5 V','≤ 5.0 Ω'][n-1]}</span></button>`).join('')}</div>
        <button class="button button-secondary wiring-record-button" data-action="record-reading" data-pin="${selectedPin}">${i('plus',17)} Log pin reading</button>
        <button class="button button-secondary wiring-full-button" data-action="open-source">${i('file',17)} Open cached schematic ${i('arrow-up-right',16)}</button>
      </section>
    </div>
    <section class="panel wiring-location-panel"><div class="wiring-location-copy"><div class="eyebrow">COMPONENT LOCATION</div><h2>Know where to look.</h2><p>Engine fuel gallery, near the secondary filter housing.</p><div class="wiring-location-tags"><span>${i('target',16)} Right side of engine</span><span class="mono">B41 · Fuel pressure</span></div><div class="wiring-location-disclaimer">Illustrated location · demo. Exact placement and access vary by engine.</div></div><div class="wiring-engine-visual"><svg viewBox="0 0 570 218" role="img" aria-label="Illustrative engine with B41 pressure sensor called out"><defs><linearGradient id="engineBody" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#475361"/><stop offset="1" stop-color="#242d37"/></linearGradient></defs><ellipse cx="279" cy="193" rx="192" ry="15" fill="#090c10" opacity=".6"/><path d="M119 82l49-37h182l62 41v86H119z" fill="url(#engineBody)" stroke="#677280"/><path d="M167 45v55l-48-18m48 18h245m-69-55v55" fill="none" stroke="#778594"/><path d="M161 116h192v56H161z" fill="#303b46" stroke="#526170"/><path d="M179 126h153m-153 9h153m-153 9h153m-153 9h153" stroke="#202931" stroke-width="4"/><rect x="175" y="31" width="161" height="20" rx="6" fill="#5d6976" stroke="#83909d"/><path d="M180 37h150" stroke="#a2acb5" opacity=".35"/><rect x="361" y="115" width="29" height="70" rx="9" fill="#879099" stroke="#a7afb6"/><rect x="395" y="117" width="24" height="63" rx="8" fill="#606f7b" stroke="#8796a3"/><rect x="358" y="113" width="64" height="11" rx="3" fill="#374551"/><path d="M371 114V93h-30v-23H221" fill="none" stroke="#828e98" stroke-width="9"/><path d="M371 114V93h-30v-23H221" fill="none" stroke="#abb3ba" stroke-width="3"/><circle cx="131" cy="146" r="38" fill="#29333c" stroke="#788692" stroke-width="4"/><circle cx="131" cy="146" r="26" fill="#141b23" stroke="#3b4651" stroke-width="5"/><circle cx="131" cy="146" r="10" fill="#687581"/><path d="M91 103l-19 3v52l23 5" fill="#34414e" stroke="#657482"/><rect x="308" y="93" width="17" height="18" rx="3" fill="#c8a45e"/><rect x="309" y="86" width="16" height="10" rx="3" fill="#2f7d89"/><circle cx="317" cy="99" r="19" fill="none" stroke="#f59e0b" stroke-width="2"/><circle cx="317" cy="99" r="26" fill="none" stroke="#f59e0b" stroke-opacity=".2"/><path d="M337 86l59-48h48" fill="none" stroke="#f59e0b" stroke-width="1.5"/><rect x="436" y="23" width="103" height="31" rx="5" fill="#342a16" stroke="#765218"/><text x="487" y="43" text-anchor="middle" fill="#fbbf24" font-size="12" font-family="Consolas,monospace">B41 SENSOR</text></svg></div></section>
  </section>`;
}

export function renderDiagnostics({ icon, checkedSteps = [] } = {}) {
  const i = (name, size = 18) => icon ? icon(name, size) : '';
  const isChecked = (n) => Array.isArray(checkedSteps) ? checkedSteps.includes(n) : checkedSteps.has(n);
  const completed = [0,1,2,3].filter(isChecked).length;
  const steps = [
    { title:'Inspect the sensor harness', body:'Key OFF. Inspect B41 and ECM connectors for loose pins, damaged insulation, corrosion, or moisture.', tag:'VISUAL INSPECTION' },
    { title:'Check the reference voltage', body:'Follow the OEM test procedure. With key ON, probe pin 1 against pin 3. Example reference: 5.0 ± 0.2 VDC.', tag:'PIN 1 → PIN 3 · VDC' },
    { title:'Verify harness continuity', body:'Key OFF; isolate the circuit as directed by the service manual. Measure signal wire end to end. Example range: ≤ 5.0 Ω.', tag:'PIN 2 → ECM J1–24 · Ω' },
    { title:'Record and verify the repair', body:'Restore all connections. Record the measurements, resolve the identified fault, then repeat the OEM verification procedure.', tag:'VERIFICATION & LOG' },
  ];
  return `<section class="diagnostic-screen screen-enter">
    <div class="diagnostic-page-heading"><div><div class="eyebrow">GUIDED TROUBLESHOOTING</div><h1>Find the fault. Fix with confidence.</h1><p class="muted">A clear next step, using the demo references on your device.</p></div><span class="badge badge-teal">${i('check',14)} DEMO DIAGNOSTICS</span></div>
    <section class="diagnostic-fault-banner"><div class="diagnostic-fault-icon">${i('alert',25)}</div><div class="diagnostic-fault-copy"><div class="diagnostic-fault-label">SAMPLE FAULT <span class="diagnostic-demo-tag">DEMO INPUT</span></div><h2><span class="mono">SPN 94 — FMI 3</span> <span class="diagnostic-fault-separator">/</span> Voltage above normal</h2><p>Fuel delivery pressure sensor · Signal circuit high</p></div><span class="diagnostic-derate">${i('alert',15)} SAMPLE DERATE</span></section>
    <div class="diagnostic-layout"><div class="diagnostic-main">
      <section class="panel diagnostic-probability-panel"><div class="panel-header"><div><span class="eyebrow">POSSIBLE ROOT CAUSES</span><h2>Illustrative possibilities.</h2></div><span class="diagnostic-model-note">Not ranked by an engine</span></div><div class="diagnostic-causes">
        <div class="diagnostic-cause diagnostic-cause-primary"><div class="diagnostic-rank mono">01</div><div class="diagnostic-cause-copy"><h3>Open circuit or short in sensor harness</h3><p>Check the signal path and connector terminals first.</p></div></div>
        <div class="diagnostic-cause"><div class="diagnostic-rank mono">02</div><div class="diagnostic-cause-copy"><h3>Faulty low-pressure transducer</h3><p>Confirm supply and harness condition before replacement.</p></div></div>
        <div class="diagnostic-cause"><div class="diagnostic-rank mono">03</div><div class="diagnostic-cause-copy"><h3>ECM reference supply issue</h3><p>Review shared reference circuits for related faults.</p></div></div>
      </div><div class="diagnostic-ranking-note">${i('info',15)} These examples demonstrate the interface only. No diagnostic probabilities are calculated.</div></section>
      <section class="panel diagnostic-checklist-panel"><div class="panel-header"><div><span class="eyebrow">GUIDED ACTION SEQUENCE</span><h2>Work the problem, step by step.</h2></div><span class="diagnostic-progress mono">${completed} / 4 DONE</span></div><div class="diagnostic-checklist">${steps.map((step,n)=>`<button class="diagnostic-step ${isChecked(n)?'is-complete':''}" data-action="check-step" data-step="${n}" aria-pressed="${isChecked(n)}"><span class="diagnostic-checkbox">${isChecked(n)?i('check',18):`<span class="mono">${n+1}</span>`}</span><span class="diagnostic-step-copy"><strong>${step.title}</strong><span class="diagnostic-step-body">${step.body}</span><span class="diagnostic-step-tag mono">${step.tag}</span></span><span class="diagnostic-step-status">${isChecked(n)?'DONE':i('plus',17)}</span></button>`).join('')}</div></section>
    </div><aside class="diagnostic-sidebar">
      <section class="panel diagnostic-context-card"><div class="diagnostic-card-icon">${i('circuit',25)}</div><div class="eyebrow">KEEP THE CIRCUIT CLOSE</div><h2>The right wire.<br>The right reading.</h2><p>Open the B41 circuit with its connector assignments and reference test values.</p><div class="diagnostic-mini-circuit"><div class="diagnostic-mini-ecm mono">ECM</div><div class="diagnostic-mini-wires"><span></span><span></span><span></span></div><div class="diagnostic-mini-sensor mono">B41</div></div><button class="button button-secondary diagnostic-full-button" data-action="go-wiring">Jump to wiring diagram ${i('arrow-right',17)}</button></section>
      <section class="panel diagnostic-verification-card"><div class="eyebrow">CLOSE THE LOOP</div><h2>Leave a clear trail.</h2><p>Save fault verification, measurements, and repair notes to this unit's local service history.</p><div class="diagnostic-completion"><div><span>Verification checklist</span><strong class="mono">${Math.round(completed/4*100)}%</strong></div><div class="diagnostic-completion-track"><span style="width:${completed/4*100}%"></span></div></div><button class="button button-primary diagnostic-full-button" data-action="log-fault">${i('check',18)} Log fault verification</button><span class="diagnostic-local-save">${i('file',13)} Local logs · export when needed</span></section>
      <div class="diagnostic-field-note">${i('info',18)}<p><strong>Verify before replacing.</strong> These example procedures must be checked against your unit's current service manual.</p></div>
    </aside></div>
  </section>`;
}

(() => {
    const input = document.getElementById('user_input');
    const submitBtn = document.getElementById('submitBtn');
    const clearBtn = document.getElementById('clearBtn');
    const clearDbBtn = document.getElementById('clearDbBtn');
    const loadingEl = document.getElementById('loading');
    const resultsEl = document.getElementById('results');
    const errorEl = document.getElementById('errorMsg');

    function setLoading(on) {
        if (on) {
            loadingEl.style.display = 'flex';
            submitBtn.disabled = true;
            clearBtn.disabled = true;
            clearDbBtn.disabled = true;
        } else {
            loadingEl.style.display = 'none';
            submitBtn.disabled = false;
            clearBtn.disabled = false;
            clearDbBtn.disabled = false;
        }
    }

    function showError(msg) { errorEl.textContent = msg || ''; errorEl.style.display = msg ? 'block' : 'none'; }

    function clearResults() { resultsEl.innerHTML = ''; }

    function mkNode(tag, cls, txt) { const el = document.createElement(tag); if (cls) el.className = cls; if (txt !== undefined) el.textContent = txt; return el }

    function renderStructured(result) {
        clearResults();
        const payload = result && result.result ? result.result : result;
        if (!payload || Object.keys(payload).length === 0) { resultsEl.appendChild(mkNode('div', 'empty', 'No results returned.')); return }

        const te = payload.task_extractor_agent && payload.task_extractor_agent.added ? payload.task_extractor_agent.added : [];
        const planner = payload.planner_agent ? payload.planner_agent : {};
        const reminder = payload.reminder_agent ? payload.reminder_agent : {};
        const reporter = payload.reporter_agent ? payload.reporter_agent : {};

        const tasksSection = mkNode('div', 'section');
        tasksSection.appendChild(mkNode('h3', null, 'Tasks'));
        if (te.length === 0) { tasksSection.appendChild(mkNode('div', 'empty', 'No tasks added')); }
        else {
            te.forEach(t => {
                const trow = mkNode('div', 'task');
                const left = mkNode('div', null);
                left.appendChild(mkNode('div', null, t.title || 'Untitled'));
                left.appendChild(mkNode('div', 'meta', (t.due ? ('Due: ' + t.due + ' • ') : '') + 'Priority: ' + (t.priority || 'Medium')));
                const right = mkNode('div', 'toolbar');
                const copyBtn = mkNode('button', 'copy-btn', 'Copy JSON');
                copyBtn.addEventListener('click', () => navigator.clipboard.writeText(JSON.stringify(t, null, 2)));
                right.appendChild(copyBtn);
                trow.appendChild(left); trow.appendChild(right);
                tasksSection.appendChild(trow);
            })
        }
        resultsEl.appendChild(tasksSection);

        const events = planner.events || [];
        const eventsSection = mkNode('div', 'section'); eventsSection.appendChild(mkNode('h3', null, 'Planned Events'));
        if (events.length === 0) eventsSection.appendChild(mkNode('div', 'empty', 'No events planned'));
        else {
            events.forEach(e => {
                const row = mkNode('div', 'task');
                const left = mkNode('div', null);
                left.appendChild(mkNode('div', null, e.title || 'Event'));
                left.appendChild(mkNode('div', 'meta', `${e.start_time || ''} • ${e.duration_mins || ''} mins`));
                const right = mkNode('div', 'toolbar');
                const cp = mkNode('button', 'copy-btn', 'Copy JSON'); cp.addEventListener('click', () => navigator.clipboard.writeText(JSON.stringify(e, null, 2)));
                right.appendChild(cp);
                row.appendChild(left); row.appendChild(right);
                eventsSection.appendChild(row);
            })
        }
        resultsEl.appendChild(eventsSection);

        const remList = reminder.reminders || [];
        const remSection = mkNode('div', 'section'); remSection.appendChild(mkNode('h3', null, 'Reminders'));
        if (remList.length === 0) remSection.appendChild(mkNode('div', 'empty', 'No reminders')); else {
            remList.forEach(r => {
                const row = mkNode('div', 'task');
                row.appendChild(mkNode('div', null, `Task ${r.task_id} • Remind at: ${r.remind_at || r.remindAt || ''}`));
                const cp = mkNode('button', 'copy-btn', 'Copy JSON'); cp.addEventListener('click', () => navigator.clipboard.writeText(JSON.stringify(r, null, 2)));
                const right = mkNode('div', 'toolbar'); right.appendChild(cp); row.appendChild(right);
                remSection.appendChild(row);
            })
        }
        resultsEl.appendChild(remSection);

        const repSection = mkNode('div', 'section'); repSection.appendChild(mkNode('h3', null, 'Report'));
        if (!reporter || Object.keys(reporter).length === 0) repSection.appendChild(mkNode('div', 'empty', 'No report')); else {
            repSection.appendChild(mkNode('div', null, reporter.summary || ''));
            repSection.appendChild(mkNode('div', 'meta', `Completed: ${reporter.completed_count || 0} • Pending: ${reporter.pending_count || 0}`));
            if ((reporter.top_actions || []).length) {
                const list = mkNode('ul', null); (reporter.top_actions || []).forEach(a => { const li = mkNode('li', null, a); list.appendChild(li) }); repSection.appendChild(list);
            }
            const cp = mkNode('button', 'copy-btn', 'Copy Raw JSON'); cp.addEventListener('click', () => navigator.clipboard.writeText(JSON.stringify(reporter, null, 2)));
            repSection.appendChild(cp);
        }
        resultsEl.appendChild(repSection);
    }

    async function runWorkflow() {
        showError(''); clearResults(); setLoading(true);
        try {
            const text = (input.value || '').trim(); if (!text) { showError('Enter some instructions to run the workflow.'); return }
            const resp = await fetch('/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
            if (!resp.ok) { const body = await resp.json().catch(() => ({ error: 'server error' })); showError(body.error || 'Workflow run failed'); return }
            const body = await resp.json(); renderStructured(body);
        } catch (err) { showError('Network error: ' + (err && err.message)); }
        finally { setLoading(false) }
    }

    if (submitBtn) submitBtn.addEventListener('click', runWorkflow);
    if (clearBtn) clearBtn.addEventListener('click', (e) => {
        // Requirement: Clear should ONLY clear the user input field.
        e.stopPropagation();
        // Use explicit DOM access per requirement
        try { document.getElementById('user_input').value = ''; } catch (err) { /* noop */ }
    });

    if (clearDbBtn) {
        clearDbBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!confirm('Clear the local DB? This will remove stored tasks.')) return;
            setLoading(true);
            try {
                // Wait for server to be reachable by checking /health
                let healthy = false;
                for (let i = 0; i < 6; i++) {
                    try {
                        const h = await fetch('/health', { method: 'GET', cache: 'no-cache' });
                        if (h.ok) { healthy = true; break; }
                    } catch (e) {
                        // server not yet reachable
                    }
                    await new Promise(r => setTimeout(r, 300));
                }
                if (!healthy) {
                    showError('Server not available. Start the Flask server and try again.');
                    return;
                }

                // Send explicit confirmation JSON required by server
                const resp = await fetch('/clear_db', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirm: true }) });
                if (!resp.ok) {
                    const errBody = await resp.json().catch(() => null);
                    const msg = errBody && errBody.error ? errBody.error : (resp.statusText || 'unknown error');
                    showError('Failed to clear DB: ' + msg);
                    return;
                }

                // show success message and clear results area
                clearResults();
                resultsEl.appendChild(mkNode('div', 'empty', 'Database cleared.'));
            } catch (err) { showError('Failed to clear DB: ' + (err && err.message)); }
            finally { setLoading(false) }
        });
    }

    // theme initialization: default to light theme unless user prefers dark
    try {
        const saved = localStorage.getItem('wf_theme');
        if (saved === 'dark') document.documentElement.classList.add('theme-dark');
        else document.documentElement.classList.remove('theme-dark');
    } catch (e) { }

    // Dashboard removed: no dashboard button handling

    setLoading(false); showError('');

    // Prefill input from URL query `?text=...` and optionally auto-run with `?auto=1`
    try {
        const params = new URLSearchParams(window.location.search);
        const pre = params.get('text');
        if (pre) {
            input.value = pre;
            if (params.get('auto') === '1') {
                // small timeout to allow UI to finish mounting
                setTimeout(() => { try { runWorkflow(); } catch (e) { /* noop */ } }, 80);
            } else {
                input.focus();
            }
        }
    } catch (e) { /* noop */ }
})();

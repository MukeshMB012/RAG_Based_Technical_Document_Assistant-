const API_BASE = '/api';

const $ = (sel) => document.querySelector(sel);
const form = $('#query-form');
const questionInput = $('#question-input');
const submitBtn = $('#submit-btn');
const btnText = submitBtn.querySelector('.btn-text');
const btnSpinner = submitBtn.querySelector('.btn-spinner');
const pipelineSection = $('#pipeline-section');
const pipelineSteps = $('#pipeline-steps');
const answerSection = $('#answer-section');
const answerContent = $('#answer-content');
const sourcesBlock = $('#sources-block');
const sourcesList = $('#sources-list');
const feedbackSection = $('#feedback-section');
const feedbackStars = $('#feedback-stars');
const feedbackText = $('#feedback-text');
const submitFeedback = $('#submit-feedback');
const feedbackResult = $('#feedback-result');
const docsModal = $('#docs-modal');
const docsContent = $('#docs-content');
const ingestModal = $('#ingest-modal');
const ingestClose = $('#ingest-close');
const ingestStatus = $('#ingest-status');

let currentResult = null;

function showToast(message, type = '') {
    const t = $('#toast');
    t.textContent = message;
    t.className = `toast ${type}`;
    t.classList.remove('hidden');
    setTimeout(() => t.classList.add('hidden'), 3500);
}

function setLoading(on) {
    submitBtn.disabled = on;
    btnText.textContent = on ? 'Processing…' : 'Ask Question';
    btnSpinner.classList.toggle('hidden', !on);
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    html = html.replace(/```([a-zA-Z0-9_]*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre class="code-block"><code class="lang-${lang}">${code.trim()}</code></pre>`;
    });

    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    html = html.replace(/^### (.*$)/gim, '<h4 style="margin: 12px 0 6px 0; color: var(--text-primary); font-size: 0.98rem;">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 style="margin: 14px 0 8px 0; color: var(--text-primary); font-size: 1.05rem;">$1</h3>');

    return html;
}

const STEP_LABELS = {
    query_analysis: 'Query Analysis',
    retrieval: 'Document Retrieval',
    document_grading: 'Document Grading',
    query_rewrite: 'Query Rewrite',
    generation: 'Answer Generation',
    groundedness_check: 'Groundedness Check',
    fallback: 'Fallback Response',
};

const STEP_ICONS = {
    completed: '✓',
    failed: '✗',
    running: '●',
    pending: '○',
    warning: '⚠',
};

function renderPipeline(trace) {
    pipelineSteps.innerHTML = '';
    pipelineSection.classList.remove('hidden');

    if (!trace || trace.length === 0) {
        pipelineSteps.innerHTML = '<p class="muted">No execution trace available.</p>';
        return;
    }

    trace.forEach((entry, idx) => {
        const step = document.createElement('div');
        step.className = 'step';

        const dotClass = entry.status || 'completed';
        const icon = STEP_ICONS[dotClass] || '○';
        const label = STEP_LABELS[entry.step] || entry.step;

        step.innerHTML = `
            <div class="step-dot ${dotClass}">${icon}</div>
            <div class="step-header" data-idx="${idx}">
                <span class="step-title">${escapeHtml(label)}</span>
                <span class="step-status ${dotClass}">${dotClass.toUpperCase()}</span>
            </div>
            <div class="step-body" id="step-body-${idx}">
                ${renderStepData(entry)}
            </div>
        `;

        pipelineSteps.appendChild(step);
    });

    document.querySelectorAll('.step-header').forEach(hdr => {
        hdr.addEventListener('click', () => {
            const body = $(`#step-body-${hdr.dataset.idx}`);
            if (body) body.classList.toggle('collapsed');
        });
    });
}

function renderStepData(entry) {
    const d = entry.data || {};

    switch (entry.step) {
        case 'query_analysis':
            return `
                <div class="step-detail">
                    <label>Original User Query</label>
                    <div class="value mono">${escapeHtml(d.original_query || '')}</div>
                </div>
                <div class="step-detail">
                    <label>Search Query</label>
                    <div class="value mono">${escapeHtml(d.search_query || '')}</div>
                </div>
            `;

        case 'retrieval':
            let html = `
                <div class="step-detail">
                    <label>Search Query</label>
                    <div class="value mono">${escapeHtml(d.query || '')}</div>
                </div>
                <div class="step-detail">
                    <label>Retrieval Attempt</label>
                    <div class="value">Attempt #${d.attempt || 1} &bull; ${d.documents_retrieved || 0} candidate chunks retrieved</div>
                </div>
            `;
            if (d.documents && d.documents.length) {
                html += d.documents.map(doc => `
                    <div class="retrieved-card">
                        <div class="retrieved-header">
                            <span class="retrieved-title">${escapeHtml(doc.id || '')}</span>
                            <span class="retrieved-distance">Cosine Distance: ${doc.distance != null ? doc.distance.toFixed(4) : ''}</span>
                        </div>
                        <div class="retrieved-source">${escapeHtml(doc.title ? `${doc.title} (${doc.source})` : doc.source)}</div>
                        <button type="button" class="grade-expand" onclick="this.nextElementSibling.classList.toggle('hidden')">Toggle Content Preview</button>
                        <div class="grade-chunk hidden">${escapeHtml(doc.content_preview || '')}</div>
                    </div>
                `).join('');
            }
            return html;

        case 'document_grading':
            let gHtml = `
                <div class="step-detail">
                    <label>Grading Results</label>
                    <div class="value">${d.relevant_count || 0} relevant out of ${d.total_count || 0} chunks evaluated</div>
                </div>
            `;
            if (d.grades && d.grades.length) {
                gHtml += d.grades.map(g => {
                    const cls = g.relevant ? 'relevant' : 'irrelevant';
                    const icon = g.relevant ? '✓' : '✗';
                    const label = g.relevant ? 'RELEVANT' : 'IRRELEVANT';
                    return `
                        <div class="grade-card ${cls}">
                            <span class="grade-icon">${icon}</span>
                            <div class="grade-info">
                                <div class="grade-title">${escapeHtml(g.document_id || '')}</div>
                                <div class="grade-label ${cls}">${label}</div>
                                <div class="grade-reason">${escapeHtml(g.reason || '')}</div>
                            </div>
                        </div>
                    `;
                }).join('');
            }
            return gHtml;

        case 'query_rewrite':
            return `
                <div class="step-detail">
                    <label>Original Query</label>
                    <div class="value mono">${escapeHtml(d.original_query || '')}</div>
                </div>
                <div class="step-detail">
                    <label>Failed Previous Query</label>
                    <div class="value mono">${escapeHtml(d.previous_query || '')}</div>
                </div>
                <div class="step-detail" style="border-left: 3px solid var(--accent, #10b981);">
                    <label>🤖 LLM Rewritten Query</label>
                    <div class="value mono bold" style="color: var(--neon-green);">${escapeHtml(d.rewritten_query || '')}</div>
                </div>
                <div class="step-detail">
                    <label>Rewrite Reasoning</label>
                    <div class="value">${escapeHtml(d.reasoning || '')}</div>
                </div>
                <span class="badge badge-accent">Retry #${d.retry_number || '?'}</span>
            `;

        case 'generation':
            return `
                <div class="step-detail">
                    <label>Context Chunks Used</label>
                    <div class="value">${d.context_chunks_used || 0} relevant chunks (irrelevant chunks filtered)</div>
                </div>
                <div class="step-detail">
                    <label>Generation Model</label>
                    <div class="value bold" style="color: var(--neon-green);">${escapeHtml(d.model || 'Gemini 3.8 Flash')}</div>
                </div>
            `;

        case 'groundedness_check':
            const isGrounded = d.grounded;
            const gcCls = isGrounded ? 'badge-green' : 'badge-amber';
            const gcLabel = isGrounded ? 'GROUNDED' : 'PARTIALLY UNGROUNDED';
            return `
                <div class="step-detail">
                    <label>Factuality Verdict</label>
                    <span class="badge ${gcCls}">${gcLabel}</span>
                </div>
                <div class="step-detail">
                    <label>Evaluation Reasoning</label>
                    <div class="value">${escapeHtml(d.reasoning || '')}</div>
                </div>
            `;

        case 'fallback':
            return `
                <div class="answer-fallback" style="text-align: left;">
                    <div class="fallback-icon">⚠</div>
                    <p class="fallback-text">${escapeHtml(d.reason || 'No relevant documentation found.')}</p>
                    <div style="margin-top: 8px;">
                        <span class="badge badge-amber">Retries Exhausted: ${d.retry_count || 0} / ${d.max_retries || 2}</span>
                    </div>
                </div>
            `;

        default:
            return `<pre class="step-detail">${escapeHtml(JSON.stringify(d, null, 2))}</pre>`;
    }
}

function renderAnswer(result) {
    answerSection.classList.remove('hidden');

    if (result.execution && result.execution.fallback_used) {
        answerContent.innerHTML = `
            <div class="answer-fallback">
                <div class="fallback-icon">⚠</div>
                <p class="fallback-text">${escapeHtml(result.answer)}</p>
                <div style="margin-top: 12px;">
                    <span class="badge badge-amber">Retry limit reached: ${result.retry_count} / ${result.execution.execution_trace.find(t => t.step === 'fallback')?.data?.max_retries || 2}</span>
                </div>
            </div>
        `;
        sourcesBlock.classList.add('hidden');
    } else {
        answerContent.innerHTML = formatMarkdown(result.answer);

        if (result.sources && result.sources.length) {
            sourcesBlock.classList.remove('hidden');
            sourcesList.innerHTML = result.sources.map(s => `
                <div class="source-item">
                    <div class="source-dot"></div>
                    <div class="source-info">
                        <div class="source-name">${escapeHtml(s.title || s.source)}</div>
                        ${s.url ? `<a class="source-url" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.url)}</a>` : ''}
                    </div>
                </div>
            `).join('');
        } else {
            sourcesBlock.classList.add('hidden');
        }
    }

    feedbackSection.classList.remove('hidden');
    feedbackResult.classList.add('hidden');
    feedbackText.value = '';
    document.querySelectorAll('.star-btn').forEach(b => b.classList.remove('active'));
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = questionInput.value.trim();
    if (!question) return;

    setLoading(true);
    pipelineSection.classList.add('hidden');
    answerSection.classList.add('hidden');

    pipelineSection.classList.remove('hidden');
    pipelineSteps.innerHTML = `
        <div class="step">
            <div class="step-dot running">●</div>
            <div class="step-header">
                <span class="step-title">Executing RAG Pipeline…</span>
                <span class="step-status running">RUNNING</span>
            </div>
        </div>
    `;

    try {
        const res = await fetch(`${API_BASE}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question }),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        currentResult = data;

        renderPipeline(data.execution?.execution_trace || []);
        renderAnswer(data);

        pipelineSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    } catch (err) {
        pipelineSteps.innerHTML = `
            <div class="step">
                <div class="step-dot failed">✗</div>
                <div class="step-header">
                    <span class="step-title">Pipeline Execution Failed</span>
                    <span class="step-status failed">FAILED</span>
                </div>
                <div class="step-body">
                    <div class="step-detail" style="border-left: 3px solid var(--red);">
                        <label>Error Details</label>
                        <div class="value">${escapeHtml(err.message)}</div>
                    </div>
                </div>
            </div>
        `;
        showToast(err.message, 'error');
    } finally {
        setLoading(false);
    }
});


document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
        questionInput.value = chip.dataset.q;
        form.dispatchEvent(new Event('submit'));
    });
});

let selectedRating = 0;

document.querySelectorAll('.star-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        selectedRating = parseInt(btn.dataset.rating, 10);
        document.querySelectorAll('.star-btn').forEach((b, i) => {
            b.classList.toggle('active', i < selectedRating);
        });
    });
});

submitFeedback.addEventListener('click', async () => {
    if (!selectedRating || !currentResult) {
        showToast('Please select a star rating first', 'error');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: currentResult.question,
                answer: currentResult.answer,
                rating: selectedRating,
                feedback: feedbackText.value,
            }),
        });

        if (!res.ok) throw new Error('Failed to record feedback');

        feedbackResult.textContent = '✓ Thank you for your feedback!';
        feedbackResult.classList.remove('hidden');
        showToast('Feedback submitted successfully!', 'success');
    } catch (err) {
        showToast(err.message, 'error');
    }
});


$('#btn-docs').addEventListener('click', async () => {
    docsModal.classList.remove('hidden');
    docsContent.innerHTML = '<p class="muted">Loading indexed documents…</p>';

    try {
        const res = await fetch(`${API_BASE}/documents`);
        if (!res.ok) throw new Error('Failed to retrieve documents');
        const data = await res.json();

        if (!data.documents || data.documents.length === 0) {
            docsContent.innerHTML = `
                <p class="muted">No documents indexed yet. Click <b>Ingest</b> to index the docs/ directory.</p>
            `;
            return;
        }

        docsContent.innerHTML = `
            <p style="margin-bottom: 12px; color: var(--text-muted); font-size: .85rem;">
                <strong>${data.total_chunks}</strong> total chunks indexed across <strong>${data.documents.length}</strong> document(s)
            </p>
            ${data.documents.map(doc => `
                <div class="doc-item">
                    <h3>${escapeHtml(doc.title)}</h3>
                    <p>${escapeHtml(doc.source)} &bull; ${doc.chunk_count} chunk(s)</p>
                    ${doc.url ? `<a href="${escapeHtml(doc.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(doc.url)}</a>` : ''}
                </div>
            `).join('')}
        `;
    } catch (err) {
        docsContent.innerHTML = `<p class="muted" style="color: var(--red);">${escapeHtml(err.message)}</p>`;
    }
});

$('#docs-close').addEventListener('click', () => docsModal.classList.add('hidden'));
docsModal.addEventListener('click', (e) => {
    if (e.target === docsModal) docsModal.classList.add('hidden');
});


const btnIngest = $('#btn-ingest');
const tabs = document.querySelectorAll('.ingest-tab');
const panes = {
    url: $('#pane-url'),
    file: $('#pane-file'),
    corpus: $('#pane-corpus'),
};

btnIngest.addEventListener('click', () => {
    ingestModal.classList.remove('hidden');
    clearIngestStatus();
});

ingestClose.addEventListener('click', () => ingestModal.classList.add('hidden'));
ingestModal.addEventListener('click', (e) => {
    if (e.target === ingestModal) ingestModal.classList.add('hidden');
});

function clearIngestStatus() {
    ingestStatus.className = 'ingest-status hidden';
    ingestStatus.textContent = '';
}

function showIngestStatus(msg, isSuccess = true) {
    ingestStatus.className = `ingest-status ${isSuccess ? 'success' : 'error'}`;
    ingestStatus.textContent = msg;
    ingestStatus.classList.remove('hidden');
}


tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const target = tab.dataset.tab;
        Object.keys(panes).forEach(k => {
            panes[k].classList.toggle('hidden', k !== target);
        });
        clearIngestStatus();
    });
});


const formIngestUrl = $('#form-ingest-url');
const inputIngestUrl = $('#input-ingest-url');
const inputIngestUrlTitle = $('#input-ingest-url-title');
const btnSubmitUrl = $('#btn-submit-url');

formIngestUrl.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = inputIngestUrl.value.trim();
    if (!url) return;

    const title = inputIngestUrlTitle.value.trim();
    btnSubmitUrl.disabled = true;
    btnSubmitUrl.querySelector('.btn-text').textContent = 'Ingesting…';
    btnSubmitUrl.querySelector('.btn-spinner').classList.remove('hidden');
    clearIngestStatus();

    try {
        const res = await fetch(`${API_BASE}/ingest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, title: title || undefined }),
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        const msg = ` Successfully indexed from URL! Created ${data.chunks_created} chunk(s). ChromaDB total: ${data.total_chunks_in_database}`;
        showIngestStatus(msg, true);
        showToast('Document indexed from URL', 'success');
        inputIngestUrl.value = '';
        inputIngestUrlTitle.value = '';
    } catch (err) {
        showIngestStatus(`✗ ${err.message}`, false);
        showToast(err.message, 'error');
    } finally {
        btnSubmitUrl.disabled = false;
        btnSubmitUrl.querySelector('.btn-text').textContent = 'Ingest from URL';
        btnSubmitUrl.querySelector('.btn-spinner').classList.add('hidden');
    }
});

// 2. Ingest via File Upload
const formIngestFile = $('#form-ingest-file');
const fileDropzone = $('#file-dropzone');
const inputIngestFile = $('#input-ingest-file');
const dropzoneText = $('#dropzone-text');
const inputIngestFileTitle = $('#input-ingest-file-title');
const btnSubmitFile = $('#btn-submit-file');
let selectedFile = null;

fileDropzone.addEventListener('click', () => inputIngestFile.click());

fileDropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileDropzone.classList.add('dragover');
});

fileDropzone.addEventListener('dragleave', () => {
    fileDropzone.classList.remove('dragover');
});

fileDropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    fileDropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFileSelection(e.dataTransfer.files[0]);
    }
});

inputIngestFile.addEventListener('change', () => {
    if (inputIngestFile.files.length > 0) {
        handleFileSelection(inputIngestFile.files[0]);
    }
});

function handleFileSelection(file) {
    selectedFile = file;
    const sizeKb = (file.size / 1024).toFixed(1);
    dropzoneText.innerHTML = `<strong>📄 ${escapeHtml(file.name)}</strong> (${sizeKb} KB)`;
    btnSubmitFile.disabled = false;
    clearIngestStatus();
}

formIngestFile.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    const title = inputIngestFileTitle.value.trim();
    btnSubmitFile.disabled = true;
    btnSubmitFile.querySelector('.btn-text').textContent = 'Uploading…';
    btnSubmitFile.querySelector('.btn-spinner').classList.remove('hidden');
    clearIngestStatus();

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        if (title) formData.append('title', title);

        const res = await fetch(`${API_BASE}/ingest`, {
            method: 'POST',
            body: formData,
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        const msg = `✓ File "${selectedFile.name}" indexed successfully! Created ${data.chunks_created} chunk(s). Total: ${data.total_chunks_in_database}`;
        showIngestStatus(msg, true);
        showToast('File indexed successfully', 'success');


        selectedFile = null;
        inputIngestFile.value = '';
        inputIngestFileTitle.value = '';
        dropzoneText.textContent = 'Click to browse or drop file here';
        btnSubmitFile.disabled = true;
    } catch (err) {
        showIngestStatus(`✗ ${err.message}`, false);
        showToast(err.message, 'error');
    } finally {
        btnSubmitFile.disabled = false;
        btnSubmitFile.querySelector('.btn-text').textContent = 'Upload & Ingest Document';
        btnSubmitFile.querySelector('.btn-spinner').classList.add('hidden');
    }
});


const btnSubmitCorpus = $('#btn-submit-corpus');

btnSubmitCorpus.addEventListener('click', async () => {
    btnSubmitCorpus.disabled = true;
    btnSubmitCorpus.querySelector('.btn-text').textContent = 'Re-indexing docs/…';
    btnSubmitCorpus.querySelector('.btn-spinner').classList.remove('hidden');
    clearIngestStatus();

    try {
        const res = await fetch(`${API_BASE}/ingest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force: true }),
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        const msg = `✓ Default corpus re-indexed! ${data.documents_loaded} doc(s) loaded into ${data.chunks_created} chunk(s). ChromaDB total: ${data.total_chunks_in_database}`;
        showIngestStatus(msg, true);
        showToast(`Corpus re-indexed: ${data.chunks_created} chunks`, 'success');
    } catch (err) {
        showIngestStatus(`✗ ${err.message}`, false);
        showToast(err.message, 'error');
    } finally {
        btnSubmitCorpus.disabled = false;
        btnSubmitCorpus.querySelector('.btn-text').textContent = 'Re-index Default Corpus';
        btnSubmitCorpus.querySelector('.btn-spinner').classList.add('hidden');
    }
});

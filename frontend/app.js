'use strict';

/**
 * Frontend of the offline AI tutoring platform.
 *
 * Every value coming from the API is inserted with `textContent` or through
 * `escapeHtml`, never through raw `innerHTML` string concatenation.
 */

const API = {
    generate: '/generate',
    evaluate: '/evaluate',
    defaultExercise: '/exercises/default',
    categories: '/learning/categories',
    topics: '/learning/topics',
    content: '/learning/content',
    search: '/learning/search',
};

/* ── Utilities ─────────────────────────────────────────────────────────── */

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

async function requestJson(url, options) {
    const response = await fetch(url, options);
    let payload = null;
    try {
        payload = await response.json();
    } catch (error) {
        payload = null;
    }
    if (!response.ok) {
        const detail = payload && payload.detail ? payload.detail : response.statusText;
        throw new Error(detail || 'Request failed');
    }
    if (!payload) {
        throw new Error('Empty response from the server');
    }
    return payload;
}

/* ── Minimal Markdown renderer (no external dependencies) ──────────────── */

function simpleMarkdown(markdown) {
    let html = escapeHtml(markdown);

    // Fenced code blocks must be handled before inline code.
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

    // Horizontal rules, blockquotes and headings.
    html = html.replace(/^---+$/gm, '<hr>');
    html = html.replace(/^&gt;\s?(.*)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/^###\s(.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^##\s(.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^#\s(.+)$/gm, '<h1>$1</h1>');

    // Lists.
    html = html.replace(/^-\s(.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    html = html.replace(/^\d+\.\s(.+)$/gm, '<li>$1</li>');

    // Inline formatting.
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Wrap the remaining plain lines into paragraphs.
    const blockTags = ['h1', 'h2', 'h3', 'ul', 'ol', 'li', 'pre', 'blockquote', 'hr', 'div'];
    const lines = html.split('\n');
    let inBlock = false;
    const result = [];

    for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line) {
            inBlock = false;
            continue;
        }
        const isBlock = blockTags.some(
            (tag) => line.startsWith('<' + tag) || line.startsWith('</' + tag)
        );
        if (isBlock) {
            inBlock = true;
            result.push(line);
        } else if (!inBlock) {
            result.push('<p>' + line + '</p>');
        } else {
            result.push(line);
        }
    }

    return result.join('\n');
}

function createGridCard(title, meta, onClick, variant) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = variant ? 'grid-card grid-card--' + variant : 'grid-card';

    const titleElement = document.createElement('div');
    titleElement.className = 'grid-card__title';
    titleElement.textContent = title;
    card.appendChild(titleElement);

    if (meta) {
        const metaElement = document.createElement('div');
        metaElement.className = 'grid-card__meta';
        metaElement.textContent = meta;
        card.appendChild(metaElement);
    }

    card.addEventListener('click', onClick);
    return card;
}

function showLoading(container, message) {
    container.replaceChildren();
    const wrapper = document.createElement('div');
    wrapper.className = 'learning-loading';

    const spinner = document.createElement('div');
    spinner.className = 'spinner';

    const text = document.createElement('p');
    text.className = 'text-gray-600';
    text.textContent = message;

    wrapper.append(spinner, text);
    container.appendChild(wrapper);
}

function showError(container, message) {
    const box = document.createElement('div');
    box.className = 'learning-error';
    box.textContent = '❌ ' + message;
    container.replaceChildren(box);
}

/* ── Tab switching ─────────────────────────────────────────────────────── */

function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach((button) => {
        button.classList.remove('active', 'active-ejercicios');
        if (button.dataset.tab === tabName) {
            button.classList.add('active');
        }
    });

    document.querySelectorAll('.tab-content').forEach((content) => {
        content.classList.remove('active');
    });

    const target = document.getElementById('tab-' + tabName);
    if (target) {
        target.classList.add('active');
    }

    if (tabName === 'learning' && !window._learningLoaded) {
        loadLearningContent();
    }
}

/* ── Learning explorer ─────────────────────────────────────────────────── */

let currentCategory = null;
let currentTopic = null;

function navigateLearning(destination, category, topic) {
    const container = document.getElementById('learningContent');
    const breadcrumbCategory = document.getElementById('bcCategory');
    const breadcrumbTopic = document.getElementById('bcTopic');
    const separator1 = document.getElementById('bcSep1');
    const separator2 = document.getElementById('bcSep2');

    if (destination === 'home') {
        currentCategory = null;
        currentTopic = null;
        breadcrumbCategory.classList.add('hidden');
        breadcrumbTopic.classList.add('hidden');
        separator1.classList.add('hidden');
        separator2.classList.add('hidden');
        showCategories(container);
        return;
    }

    if (destination === 'category') {
        currentCategory = category;
        currentTopic = null;
        breadcrumbCategory.textContent = category;
        breadcrumbCategory.classList.remove('hidden');
        breadcrumbTopic.classList.add('hidden');
        separator1.classList.remove('hidden');
        separator2.classList.add('hidden');
        showTopics(container, category);
        return;
    }

    if (destination === 'topic') {
        currentTopic = topic;
        breadcrumbTopic.textContent = topic.substring(0, 60);
        breadcrumbTopic.classList.remove('hidden');
        separator2.classList.remove('hidden');
        showContent(container, topic, category);
    }
}

async function showCategories(container) {
    showLoading(container, 'Loading categories...');

    try {
        const data = await requestJson(API.categories);

        if (data.status !== 'success' || !data.categorias || data.categorias.length === 0) {
            showError(container, 'No documentation is available in the vector store.');
            return;
        }

        container.replaceChildren();

        const heading = document.createElement('h1');
        heading.textContent = '📚 Documentation Categories';

        const subtitle = document.createElement('p');
        subtitle.textContent = 'Pick a category to explore the available topics.';

        const grid = document.createElement('div');
        grid.className = 'card-grid';

        data.categorias.forEach((category) => {
            grid.appendChild(
                createGridCard(
                    category.categoria,
                    category.total + ' chunks',
                    () => navigateLearning('category', category.categoria),
                    'green'
                )
            );
        });

        container.append(heading, subtitle, grid);
    } catch (error) {
        showError(container, 'Connection error while loading categories.');
    }
}

async function showTopics(container, category) {
    showLoading(container, 'Loading topics...');

    try {
        const url = API.topics + '?categoria=' + encodeURIComponent(category);
        const data = await requestJson(url);

        if (data.status !== 'success' || !data.temas || data.temas.length === 0) {
            showError(container, 'No topics are available in this category.');
            return;
        }

        container.replaceChildren();

        const heading = document.createElement('h1');
        heading.textContent = '📖 ' + category;

        const subtitle = document.createElement('p');
        subtitle.textContent = 'Topics available in this category. Click one to read it.';

        const grid = document.createElement('div');
        grid.className = 'card-grid';

        data.temas.forEach((topic) => {
            grid.appendChild(
                createGridCard(
                    topic.tema.substring(0, 80),
                    topic.total_chunks + ' sections',
                    () => navigateLearning('topic', category, topic.tema)
                )
            );
        });

        container.append(heading, subtitle, grid);
    } catch (error) {
        showError(container, 'Could not load the topics of this category.');
    }
}

async function showContent(container, topic, category) {
    showLoading(container, 'Loading content...');

    try {
        let url = API.content + '?tema=' + encodeURIComponent(topic);
        if (category) {
            url += '&categoria=' + encodeURIComponent(category);
        }

        const data = await requestJson(url);

        if (data.status !== 'success' || !data.contenido || data.contenido.length === 0) {
            showError(container, 'No content is available for this topic.');
            return;
        }

        container.replaceChildren();

        const heading = document.createElement('h1');
        heading.textContent = topic.substring(0, 100);
        container.appendChild(heading);

        const sections = {};
        data.contenido.forEach((item) => {
            const section = item.seccion || 'General';
            if (!sections[section]) {
                sections[section] = [];
            }
            sections[section].push(item.contenido);
        });

        Object.keys(sections).forEach((sectionName) => {
            const sectionHeading = document.createElement('h2');
            sectionHeading.textContent = sectionName;
            container.appendChild(sectionHeading);

            sections[sectionName].forEach((document) => {
                const chunk = document.createElement('div');
                chunk.className = 'content-chunk';
                chunk.innerHTML = simpleMarkdown(document);
                container.appendChild(chunk);
            });
        });

        const source = document.createElement('p');
        source.style.fontSize = '0.8rem';
        source.style.color = '#9ca3af';
        source.textContent = 'Source: ' + (category || 'various');
        container.appendChild(source);
    } catch (error) {
        showError(container, 'Could not load the content of this topic.');
    }
}

async function loadLearningContent() {
    navigateLearning('home');
    window._learningLoaded = true;
}

/* ── Semantic search ───────────────────────────────────────────────────── */

async function runSearch() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) {
        return;
    }

    const results = document.getElementById('searchResults');
    results.classList.remove('hidden');
    showLoading(results, 'Searching the documentation...');

    try {
        const data = await requestJson(API.search + '?q=' + encodeURIComponent(query));

        if (data.status !== 'success' || !data.resultados || data.resultados.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'learning-empty';
            empty.textContent = '🔍 No results found for "' + query + '".';
            results.replaceChildren(empty);
            return;
        }

        results.replaceChildren();

        const wrapper = document.createElement('div');
        wrapper.style.background = '#f0fdf4';
        wrapper.style.border = '1px solid #bbf7d0';
        wrapper.style.borderRadius = '0.5rem';
        wrapper.style.padding = '1rem';

        const heading = document.createElement('div');
        heading.style.fontWeight = '600';
        heading.style.color = '#166534';
        heading.style.marginBottom = '0.75rem';
        heading.textContent = '🔍 Results for: "' + query + '"';
        wrapper.appendChild(heading);

        data.resultados.forEach((result) => {
            const card = document.createElement('div');
            card.style.background = '#ffffff';
            card.style.border = '1px solid #e5e7eb';
            card.style.borderRadius = '0.375rem';
            card.style.padding = '0.75rem';
            card.style.marginBottom = '0.5rem';

            const meta = document.createElement('div');
            meta.style.fontSize = '0.75rem';
            meta.style.fontWeight = '600';
            meta.style.marginBottom = '0.25rem';
            meta.style.color = result.relevancia > 70 ? '#166534' : result.relevancia > 40 ? '#ca8a04' : '#6b7280';
            meta.textContent = '🔗 ' + result.tema.substring(0, 60) + ' — Relevance: ' + result.relevancia + '%';

            const body = document.createElement('div');
            body.className = 'learning-content';
            body.style.fontSize = '0.875rem';
            body.innerHTML = simpleMarkdown(result.contenido.substring(0, 300));

            const source = document.createElement('div');
            source.style.fontSize = '0.7rem';
            source.style.color = '#9ca3af';
            source.style.marginTop = '0.25rem';
            source.textContent = result.fuente || '';

            card.append(meta, body, source);
            wrapper.appendChild(card);
        });

        results.appendChild(wrapper);
    } catch (error) {
        showError(results, 'The search could not be completed.');
    }
}

/* ── Exercise generation ───────────────────────────────────────────────── */

async function onGenerate(event) {
    event.preventDefault();

    const button = document.getElementById('btnGenerate');
    const loading = document.getElementById('loadingGenerate');
    const result = document.getElementById('resultGenerate');

    button.disabled = true;
    loading.classList.remove('hidden');
    result.classList.add('hidden');

    const formData = new FormData();
    formData.append('student_id', document.getElementById('studentIdGenerate').value);
    formData.append('topic', document.getElementById('topicInput').value);

    try {
        const data = await requestJson(API.generate, { method: 'POST', body: formData });

        loading.classList.add('hidden');

        if (data.status === 'success' && data.data) {
            document.getElementById('instructionsUI').textContent = data.data.instructions;
            document.getElementById('exampleUI').textContent =
                data.data.expected_example || 'No example was provided.';
            document.getElementById('starterCodeUI').textContent = data.data.starter_code;
            result.classList.remove('hidden');

            // Carry the student id over to the evaluation form for convenience.
            document.getElementById('studentIdEvaluate').value =
                document.getElementById('studentIdGenerate').value;
        } else {
            window.alert('Error: ' + (data.message || 'unknown error'));
        }
    } catch (error) {
        loading.classList.add('hidden');
        window.alert('Connection error: ' + error.message);
    } finally {
        button.disabled = false;
    }
}

/* ── Built-in exercise ─────────────────────────────────────────────────── */

async function loadDefaultExercise() {
    const button = document.getElementById('btnDefaultExercise');
    button.disabled = true;

    try {
        const data = await requestJson(API.defaultExercise);

        if (data.status !== 'success' || !data.data) {
            window.alert('Error: ' + (data.message || 'no built-in exercise available'));
            return;
        }

        document.getElementById('instructionsUI').textContent = data.data.instructions;
        document.getElementById('exampleUI').textContent =
            data.data.expected_example || 'No example was provided.';
        document.getElementById('starterCodeUI').textContent = data.data.starter_code;
        document.getElementById('resultGenerate').classList.remove('hidden');
        document.getElementById('exerciseId').value = 'default';
    } catch (error) {
        window.alert('Connection error: ' + error.message);
    } finally {
        button.disabled = false;
    }
}

/* ── Evaluation ────────────────────────────────────────────────────────── */

async function onEvaluate(event) {
    event.preventDefault();

    const button = document.getElementById('btnEvaluate');
    const container = document.getElementById('resultContainer');
    const loading = document.getElementById('loadingEvaluate');
    const responseBox = document.getElementById('responseBox');
    const badge = document.getElementById('statusBadge');
    const message = document.getElementById('messageText');

    const fileInput = document.getElementById('fileInput');
    if (!fileInput.files || fileInput.files.length === 0) {
        window.alert('Select a .py file first.');
        return;
    }

    const formData = new FormData();
    formData.append('student_id', document.getElementById('studentIdEvaluate').value);
    formData.append('exercise_id', document.getElementById('exerciseId').value);
    formData.append('file', fileInput.files[0]);

    button.disabled = true;
    container.classList.remove('hidden');
    responseBox.classList.add('hidden');
    loading.classList.remove('hidden');

    try {
        const data = await requestJson(API.evaluate, { method: 'POST', body: formData });

        loading.classList.add('hidden');
        responseBox.classList.remove('hidden');

        if (data.status === 'success') {
            badge.textContent = '✅ Success';
            badge.className = 'badge badge-success';
            message.textContent = data.message || 'All tests passed.';
        } else if (data.status === 'failure') {
            badge.textContent = '🧠 Tutor Feedback';
            badge.className = 'badge badge-warning';
            message.textContent = data.tutor_feedback || 'The tutor did not return any feedback.';
        } else {
            badge.textContent = '⚠️ Technical Error';
            badge.className = 'badge badge-error';
            message.textContent = data.message || 'Unknown error';
        }
    } catch (error) {
        loading.classList.add('hidden');
        responseBox.classList.remove('hidden');
        badge.textContent = '❌ Connection Error';
        badge.className = 'badge badge-error';
        message.textContent = 'Could not reach the local server.';
    } finally {
        button.disabled = false;
    }
}

/* ── Bootstrap ─────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tab-btn').forEach((button) => {
        button.addEventListener('click', () => switchTab(button.dataset.tab));
    });

    document.getElementById('bcCategories').addEventListener('click', () => navigateLearning('home'));
    document.getElementById('searchBtn').addEventListener('click', runSearch);
    document.getElementById('searchInput').addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            runSearch();
        }
    });

    document.getElementById('generateForm').addEventListener('submit', onGenerate);
    document.getElementById('evaluationForm').addEventListener('submit', onEvaluate);
    document.getElementById('btnDefaultExercise').addEventListener('click', loadDefaultExercise);
});

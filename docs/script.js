// script.js - MediaTools
// youtube downloader (cobalt API) + file converter + compressor (ffmpeg.wasm 0.11.x)
// nothing runs on a server — it's all browser-side

// =====================================================================
//  TABS
// =====================================================================

function switchTab(name, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.remove('hidden');
    btn.classList.add('active');
}


// =====================================================================
//  TÉLÉCHARGER — cobalt API
// =====================================================================

// Official cobalt API + community instances
// Tried in order: direct first, then via CORS proxy as last resort
// cobalt v10+ API: POST to root URL (no /api suffix)
const COBALT_INSTANCES = [
    'https://api.cobalt.tools',
    'https://cobalt.imput.net',
    'https://cob.freetards.xyz',
    'https://cobalt.synzr.space',
];

// Public CORS proxy used as fallback when direct calls fail (e.g. local file:// testing)
// corsproxy.io wraps the request server-side and forwards it
const CORS_PROXY = 'https://corsproxy.io/?url=';

document.getElementById('yt-mode').addEventListener('change', function () {
    const audioOnly = this.value === 'audio';
    document.getElementById('yt-vq-wrap').style.display = audioOnly ? 'none' : '';
    document.getElementById('yt-vc-wrap').style.display = audioOnly ? 'none' : '';
});

document.getElementById('yt-af').addEventListener('change', function () {
    const isLossless = ['wav', 'flac'].includes(this.value);
    const wrap = document.getElementById('yt-ab-wrap');
    wrap.style.opacity = isLossless ? '0.35' : '';
    wrap.style.pointerEvents = isLossless ? 'none' : '';
});

function ytOpenInCobalt() {
    const url = document.getElementById('yt-url').value.trim();
    window.open(url ? 'https://cobalt.tools/#' + encodeURIComponent(url) : 'https://cobalt.tools', '_blank');
}

async function ytDownload() {
    const url = document.getElementById('yt-url').value.trim();
    if (!url) { showStatus('yt-status', 'error', 'Collez une URL d\'abord.'); return; }

    const payload = {
        url,
        videoQuality: document.getElementById('yt-vq').value,
        audioFormat: document.getElementById('yt-af').value,
        audioBitrate: document.getElementById('yt-ab').value,
        filenameStyle: document.getElementById('yt-filename').value,
        videoCodec: document.getElementById('yt-vcodec').value,
        downloadMode: (() => {
            const mode = document.getElementById('yt-mode').value;
            const mute = document.getElementById('yt-mute-audio').checked;
            return mode === 'audio' ? 'audio' : (mode === 'mute' || mute ? 'mute' : 'auto');
        })(),
    };

    showStatus('yt-status', 'info', 'Contacting cobalt API...');

    // Step 1: try all instances directly
    let lastError = null;
    for (let i = 0; i < COBALT_INSTANCES.length; i++) {
        const instance = COBALT_INSTANCES[i];
        if (i > 0) showStatus('yt-status', 'info', `Instance ${i} indisponible, essai de ${instance}...`);
        try {
            const ok = await tryCobaltInstance(instance, payload);
            if (ok) return;
        } catch (err) {
            lastError = err;
            console.warn(`cobalt [${instance}] failed:`, err.message);
        }
    }

    // Step 2: retry first instance through CORS proxy (works from file:// or blocked origins)
    showStatus('yt-status', 'info', 'Échec direct, essai via proxy CORS...');
    try {
        const proxied = CORS_PROXY + encodeURIComponent(COBALT_INSTANCES[0]);
        const ok = await tryCobaltInstance(proxied, payload);
        if (ok) return;
    } catch (err) {
        lastError = err;
        console.warn('cobalt proxy failed:', err.message);
    }

    showStatus('yt-status', 'error',
        `Téléchargement échoué : ${lastError ? lastError.message : 'toutes les instances ont échoué'}\n\n` +
        `Utilisez "Ouvrir dans Cobalt" pour accéder directement au site.`
    );
}

async function tryCobaltInstance(instanceUrl, payload) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    let res;
    try {
        res = await fetch(instanceUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal,
        });
    } finally {
        clearTimeout(timeout);
    }

    if (!res.ok) {
        let errText = `HTTP ${res.status}`;
        try { const j = await res.json(); errText += ': ' + (j?.error?.code || JSON.stringify(j)); } catch (_) {}
        throw new Error(errText);
    }

    const data = await res.json();
    console.log(`cobalt [${instanceUrl}] →`, data);

    if (data.status === 'error') throw new Error(`cobalt error: ${data.error?.code || 'unknown'}`);

    if (['redirect', 'tunnel', 'stream'].includes(data.status)) {
        const fname = data.filename || 'download';
        showStatus('yt-status', 'success', `Téléchargement de "${fname}"...`);
        triggerDownload(data.url, fname);
        return true;
    }

    if (data.status === 'picker') {
        const items = data.picker || [];
        if (!items.length) throw new Error('picker: no items');
        let html = `<strong>${items.length} flux disponibles — cliquez pour télécharger :</strong><br><br>`;
        items.forEach((item, i) => {
            const label = item.type || `Stream ${i + 1}`;
            const thumb = item.thumb ? `<img src="${item.thumb}" style="height:36px;vertical-align:middle;margin-right:6px;border-radius:3px">` : '';
            html += `${thumb}<a href="${item.url}" target="_blank" rel="noopener" style="color:#60a5fa">${label}</a><br>`;
        });
        const el = document.getElementById('yt-status');
        el.className = 'status info';
        el.innerHTML = html;
        el.classList.remove('hidden');
        return true;
    }

    throw new Error(`unexpected cobalt status: ${data.status}`);
}

function triggerDownload(url, filename) {
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.target = '_blank'; a.rel = 'noopener';
    document.body.appendChild(a); a.click();
    setTimeout(() => document.body.removeChild(a), 500);
}


// =====================================================================
//  FFMPEG 0.11.x — shared instance
//  API: createFFmpeg / ffmpeg.FS / ffmpeg.run / fetchFile
// =====================================================================

// Global ffmpeg instance (shared between Convert and Compress tabs)
// Progress events are routed via ffProgressCallback — set it before each run
let ffmpeg = null;
let ffLoading = false;
let ffProgressCallback = null; // (pct: number) => void — swapped per-tab

async function loadFFmpeg(onProgress) {
    ffProgressCallback = onProgress || null;

    if (ffmpeg && ffmpeg.isLoaded()) return; // already ready

    if (ffLoading) {
        // another tab triggered loading, wait for it
        while (ffLoading) await sleep(100);
        return;
    }

    ffLoading = true;

    if (typeof FFmpeg === 'undefined' || !FFmpeg.createFFmpeg) {
        ffLoading = false;
        throw new Error('FFmpeg library did not load — vérifiez votre connexion et rechargez la page.');
    }

    try {
        const { createFFmpeg } = FFmpeg;

        ffmpeg = createFFmpeg({
            corePath: 'https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.11.0/dist/ffmpeg-core.js',
            log: false,
            progress: ({ ratio }) => {
                const pct = Math.min(99, Math.round(ratio * 100));
                if (ffProgressCallback) ffProgressCallback(pct);
            },
        });

        await ffmpeg.load();
        ffLoading = false;
        console.log('ffmpeg 0.11.x loaded OK');

    } catch (err) {
        ffLoading = false;
        ffmpeg = null;
        throw new Error('Échec du chargement de FFmpeg : ' + err.message +
            '\nAssurez-vous que la page est servie via HTTP (pas file://) ou essayez un autre navigateur.');
    }
}

// Write → run → read → unlink helper
async function ffRun(inputName, inputFile, outputName, args) {
    const { fetchFile } = FFmpeg;
    ffmpeg.FS('writeFile', inputName, await fetchFile(inputFile));
    console.log('ffmpeg run:', ['-i', inputName, ...args, outputName].join(' '));
    await ffmpeg.run('-i', inputName, ...args, outputName);
    const data = ffmpeg.FS('readFile', outputName);
    try { ffmpeg.FS('unlink', inputName); } catch (_) {}
    try { ffmpeg.FS('unlink', outputName); } catch (_) {}
    return data;
}


// =====================================================================
//  FILE UTILS
// =====================================================================

const VIDEO_EXTS = new Set(['mp4','mkv','avi','mov','webm','flv','wmv','ts','m2ts','mts','vob','rm','rmvb','3gp']);
const AUDIO_EXTS = new Set(['mp3','aac','m4a','flac','wav','ogg','opus','wma','aiff','aif','ac3','dts','mka']);

const OUTPUT_FORMATS = {
    video: ['mp4','mkv','webm','avi','mov','ts','gif','mp3','aac','m4a','flac','wav','ogg','opus'],
    audio: ['mp3','aac','m4a','flac','wav','ogg','opus','aiff'],
};
const AUDIO_OUTPUT_FORMATS = ['mp3','aac','m4a','flac','wav','ogg','opus','aiff'];
const VIDEO_OUTPUT_FORMATS = ['mp4','mkv','webm','avi','mov','ts'];

const AUDIO_CODEC_DEFAULTS = {
    mp4:'aac', mkv:'aac', webm:'libvorbis', avi:'libmp3lame', mov:'aac', ts:'aac',
    gif: null,
    mp3:'libmp3lame', aac:'aac', m4a:'aac', ogg:'libvorbis',
    opus:'libopus', flac:'flac', wav:'pcm_s16le', aiff:'pcm_s16le',
};

function getExt(filename) { return filename.split('.').pop().toLowerCase(); }

function getFileType(filename) {
    const ext = getExt(filename);
    if (VIDEO_EXTS.has(ext)) return 'video';
    if (AUDIO_EXTS.has(ext)) return 'audio';
    return 'video';
}

function getMimeType(ext) {
    return { mp4:'video/mp4', mkv:'video/x-matroska', webm:'video/webm', avi:'video/x-msvideo',
        mov:'video/quicktime', flv:'video/x-flv', ts:'video/mp2t', gif:'image/gif',
        mp3:'audio/mpeg', aac:'audio/aac', m4a:'audio/mp4', flac:'audio/flac',
        wav:'audio/wav', ogg:'audio/ogg', opus:'audio/opus', aiff:'audio/aiff',
    }[ext] || 'application/octet-stream';
}

function sizeStr(bytes) {
    if (bytes > 1024**3) return (bytes / 1024**3).toFixed(2) + ' GB';
    return (bytes / 1024**2).toFixed(2) + ' MB';
}

function resultHTML(dlName, blobUrl, origBytes, newBytes) {
    const origMB = (origBytes / 1024**2).toFixed(2);
    const newMB  = (newBytes  / 1024**2).toFixed(2);
    const delta  = newBytes < origBytes
        ? `&#8595; ${((1 - newBytes / origBytes) * 100).toFixed(1)}% plus léger`
        : `&#8593; ${((newBytes / origBytes - 1) * 100).toFixed(1)}% plus lourd`;
    return `<div class="result-box">
        <p>Terminé ! &nbsp;·&nbsp; <strong>${dlName}</strong><br>${origMB} MB &rarr; ${newMB} MB &nbsp;(${delta})</p>
        <a href="${blobUrl}" download="${dlName}" class="btn-primary">&#8681; Télécharger</a>
    </div>`;
}


// =====================================================================
//  CONVERTIR TAB
// =====================================================================

let currentConvertFile = null;
let currentConvertFileType = null;

(function setupConvertDrop() {
    const zone  = document.getElementById('convert-drop-zone');
    const input = document.getElementById('convert-file-input');
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('drag-over'); if (e.dataTransfer.files[0]) handleConvertFile(e.dataTransfer.files[0]); });
    input.addEventListener('change', e => { if (e.target.files[0]) handleConvertFile(e.target.files[0]); });
})();

function handleConvertFile(file) {
    currentConvertFile = file;
    currentConvertFileType = getFileType(file.name);

    document.getElementById('convert-file-info').innerHTML =
        `<strong>${file.name}</strong> &nbsp;·&nbsp; ${sizeStr(file.size)} &nbsp;·&nbsp; type : ${currentConvertFileType}`;

    const fmtSel = document.getElementById('out-format');
    fmtSel.innerHTML = '';
    const inputExt = getExt(file.name);
    OUTPUT_FORMATS[currentConvertFileType].forEach(fmt => {
        const opt = document.createElement('option');
        opt.value = fmt; opt.textContent = fmt.toUpperCase();
        if (fmt === 'mp4' && currentConvertFileType === 'video') opt.selected = true;
        else if (fmt === 'mp3' && currentConvertFileType === 'audio') opt.selected = true;
        else if (fmt === inputExt) opt.selected = true;
        fmtSel.appendChild(opt);
    });

    document.getElementById('video-section').style.display = currentConvertFileType === 'video' ? '' : 'none';
    setAudioCodecDefault();
    fmtSel.onchange = () => { setAudioCodecDefault(); toggleAudioOutputSettings(); };
    document.getElementById('convert-file-settings').classList.remove('hidden');
    document.getElementById('convert-result').classList.add('hidden');
    document.getElementById('convert-progress-wrap').classList.add('hidden');
    toggleAudioOutputSettings();
}

function setAudioCodecDefault() {
    const fmt = document.getElementById('out-format').value;
    const def = AUDIO_CODEC_DEFAULTS[fmt];
    if (!def) return;
    const sel = document.getElementById('a-codec');
    for (const opt of sel.options) { if (opt.value === def) { opt.selected = true; break; } }
    onACodecChange();
}

function onACodecChange() {
    const codec = document.getElementById('a-codec').value;
    const lossless = ['flac','pcm_s16le','pcm_s24le','pcm_s32le','copy'].includes(codec);
    const wrap = document.getElementById('a-bitrate-wrap');
    wrap.style.opacity = lossless ? '0.35' : '';
    wrap.style.pointerEvents = lossless ? 'none' : '';
}

function onVCodecChange() {
    const isCopy = document.getElementById('v-codec').value === 'copy';
    ['crf-wrap','preset-wrap'].forEach(id => {
        const el = document.getElementById(id);
        el.style.opacity = isCopy ? '0.35' : '';
        el.style.pointerEvents = isCopy ? 'none' : '';
    });
}

function toggleAudioOutputSettings() {
    const fmt = document.getElementById('out-format').value;
    const isAudioOut = AUDIO_EXTS.has(fmt) || ['mp3','aac','m4a','ogg','opus','flac','wav','aiff'].includes(fmt);
    if (currentConvertFileType === 'video') {
        document.getElementById('video-section').style.display = isAudioOut ? 'none' : '';
    }
}

function resetConvertFile() {
    currentConvertFile = null; currentConvertFileType = null;
    document.getElementById('convert-file-input').value = '';
    document.getElementById('convert-file-settings').classList.add('hidden');
}

async function startConvert() {
    if (!currentConvertFile) return;

    const outFormat = document.getElementById('out-format').value;
    const inputExt  = getExt(currentConvertFile.name);

    const pwrap = document.getElementById('convert-progress-wrap');
    const pfill = document.getElementById('convert-progress-fill');
    pwrap.classList.remove('hidden');
    document.getElementById('convert-result').classList.add('hidden');
    pfill.className = '';
    setP('convert', 0, 'Démarrage...', 'Premier chargement : 10–30s, plus rapide ensuite.');

    try {
        await loadFFmpeg(pct => setP('convert', pct, `Conversion... ${pct}%`, ''));

        setP('convert', 0, 'Lecture du fichier...', '');

        const trimStart = document.getElementById('trim-start').value.trim();
        const trimEnd   = document.getElementById('trim-end').value.trim();

        // trim args go before -i for fast seek
        const beforeInput = trimStart ? ['-ss', trimStart] : [];
        const afterInput  = trimEnd   ? ['-to', trimEnd]   : [];

        const convArgs = buildFFmpegArgs(outFormat, currentConvertFileType);
        // for 0.11.x, we can't put args before -i via the helper, so we build manually
        const fullArgs = [...afterInput, ...convArgs, outFormat === 'ts' ? [] : []].flat();

        // ffmpeg.run in 0.11.x doesn't support args before -i; trim via -ss after -i instead
        const runArgs = [...afterInput, ...convArgs];

        const inputName  = 'input.'  + inputExt;
        const outputName = 'output.' + outFormat;
        setP('convert', 0, 'Conversion en cours...', '');

        const outputData = await ffRun(inputName, currentConvertFile, outputName, runArgs);
        const blob    = new Blob([outputData.buffer], { type: getMimeType(outFormat) });
        const blobUrl = URL.createObjectURL(blob);
        const dlName  = currentConvertFile.name.replace(/\.[^/.]+$/, '') + '_converted.' + outFormat;

        document.getElementById('convert-result').innerHTML = resultHTML(dlName, blobUrl, currentConvertFile.size, blob.size);
        document.getElementById('convert-result').classList.remove('hidden');
        setP('convert', 100, 'Terminé !', '');
        pfill.classList.add('done');

    } catch (err) {
        console.error('convert failed:', err);
        setP('convert', 0, 'Erreur : ' + err.message, 'Ouvrez la console (F12) pour plus de détails.');
        pfill.classList.add('error');
    }
}

function buildFFmpegArgs(outputFormat, fileType) {
    const args = [];
    const isAudioOut = ['mp3','aac','m4a','flac','wav','ogg','opus','aiff'].includes(outputFormat);

    if (fileType === 'video' && !isAudioOut) {
        const vCodec    = document.getElementById('v-codec').value;
        const preset    = document.getElementById('v-preset').value;
        const crf       = document.getElementById('v-crf').value;
        const vBitrate  = parseInt(document.getElementById('v-bitrate').value) || 0;
        const vMaxrate  = parseInt(document.getElementById('v-maxrate').value) || 0;
        const res       = document.getElementById('v-res').value;
        const fps       = document.getElementById('v-fps').value;
        const pixFmt    = document.getElementById('v-pixel').value;
        const stripAudio = document.getElementById('v-strip-audio').value;
        const deinterlace = document.getElementById('v-deinterlace').checked;

        if (vCodec === 'copy') {
            args.push('-c:v', 'copy');
        } else {
            args.push('-c:v', vCodec);
            if (vCodec === 'libvpx-vp9') {
                const vp9map = { ultrafast:'realtime', superfast:'realtime', veryfast:'realtime', faster:'good', fast:'good', medium:'good', slow:'best', slower:'best', veryslow:'best' };
                args.push('-deadline', vp9map[preset] || 'good');
                if (vBitrate > 0) args.push('-b:v', vBitrate + 'k');
                else args.push('-crf', crf, '-b:v', '0');
            } else {
                args.push('-preset', preset);
                if (vBitrate > 0) {
                    args.push('-b:v', vBitrate + 'k');
                    if (vMaxrate > 0) { args.push('-maxrate', vMaxrate + 'k', '-bufsize', (vMaxrate * 2) + 'k'); }
                } else {
                    args.push('-crf', crf);
                }
            }
            if (pixFmt) args.push('-pix_fmt', pixFmt);
        }

        const vf = [];
        if (deinterlace) vf.push('yadif=0:-1:0');
        if (res) vf.push(`scale=${res}:flags=lanczos`);
        if (vf.length) args.push('-vf', vf.join(','));
        if (fps) args.push('-r', fps);

        if (stripAudio === 'strip') args.push('-an');
        else args.push(...buildAudioArgs());

    } else {
        args.push('-vn');
        args.push(...buildAudioArgs());
    }

    if (outputFormat === 'mp4' || outputFormat === 'mov') args.push('-movflags', '+faststart');
    if (outputFormat === 'ts') args.push('-f', 'mpegts');

    if (outputFormat === 'gif') {
        const scale  = document.getElementById('v-res').value || '320:-1';
        const gifFps = document.getElementById('v-fps').value || '15';
        const vfIdx  = args.indexOf('-vf');
        if (vfIdx !== -1) args.splice(vfIdx, 2);
        args.push('-an', '-vf', `fps=${gifFps},scale=${scale}:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=bayer`);
    }

    return args;
}

function buildAudioArgs() {
    const args = [];
    const codec     = document.getElementById('a-codec').value;
    const bitrate   = document.getElementById('a-bitrate').value;
    const sr        = document.getElementById('a-samplerate').value;
    const ch        = document.getElementById('a-channels').value;
    const vol       = parseInt(document.getElementById('a-volume').value);
    const normalize = document.getElementById('a-normalize').checked;

    if (codec === 'copy') { args.push('-c:a', 'copy'); return args; }

    args.push('-c:a', codec);
    const lossless = ['flac','pcm_s16le','pcm_s24le','pcm_s32le'];
    if (!lossless.includes(codec)) args.push('-b:a', bitrate);
    if (sr) args.push('-ar', sr);
    if (ch) args.push('-ac', ch);

    const af = [];
    if (vol !== 100) af.push(`volume=${(vol / 100).toFixed(3)}`);
    if (normalize) af.push('loudnorm=I=-14:LRA=11:TP=-1');
    if (af.length) args.push('-af', af.join(','));

    return args;
}


// =====================================================================
//  COMPRESSER TAB
// =====================================================================

let currentCompressFile = null;
let currentCompressFileType = null;

(function setupCompressDrop() {
    const zone  = document.getElementById('compress-drop-zone');
    const input = document.getElementById('compress-file-input');
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('drag-over'); if (e.dataTransfer.files[0]) handleCompressFile(e.dataTransfer.files[0]); });
    input.addEventListener('change', e => { if (e.target.files[0]) handleCompressFile(e.target.files[0]); });
})();

function handleCompressFile(file) {
    currentCompressFile = file;
    currentCompressFileType = getFileType(file.name);
    const isAudio = currentCompressFileType === 'audio';

    document.getElementById('compress-file-info').innerHTML =
        `<strong>${file.name}</strong> &nbsp;·&nbsp; ${sizeStr(file.size)} &nbsp;·&nbsp; type : ${currentCompressFileType}`;

    document.getElementById('compress-video-section').style.display = isAudio ? 'none' : '';

    const fmtSel = document.getElementById('compress-format');
    fmtSel.innerHTML = '';
    const inputExt = getExt(file.name);
    const sameOpt = document.createElement('option');
    sameOpt.value = 'same'; sameOpt.textContent = `Même format (${inputExt.toUpperCase()})`; sameOpt.selected = true;
    fmtSel.appendChild(sameOpt);
    (isAudio ? AUDIO_OUTPUT_FORMATS : VIDEO_OUTPUT_FORMATS).forEach(fmt => {
        if (fmt === inputExt) return;
        const opt = document.createElement('option');
        opt.value = fmt; opt.textContent = fmt.toUpperCase();
        fmtSel.appendChild(opt);
    });

    document.getElementById('compress-settings').classList.remove('hidden');
    document.getElementById('compress-result').classList.add('hidden');
    document.getElementById('compress-progress-wrap').classList.add('hidden');
}

function onCompressPresetChange() {
    const val = document.getElementById('compress-preset').value;
    document.getElementById('compress-crf-wrap').classList.toggle('hidden', val !== 'custom');
}

function resetCompressFile() {
    currentCompressFile = null; currentCompressFileType = null;
    document.getElementById('compress-file-input').value = '';
    document.getElementById('compress-settings').classList.add('hidden');
}

async function startCompress() {
    if (!currentCompressFile) return;

    const inputExt  = getExt(currentCompressFile.name);
    const formatSel = document.getElementById('compress-format').value;
    const outFormat = formatSel === 'same' ? inputExt : formatSel;
    const isAudio   = currentCompressFileType === 'audio';

    const pfill = document.getElementById('compress-progress-fill');
    document.getElementById('compress-progress-wrap').classList.remove('hidden');
    document.getElementById('compress-result').classList.add('hidden');
    pfill.className = '';
    setP('compress', 0, 'Démarrage...', 'Premier chargement : 10–30s, plus rapide ensuite.');

    try {
        await loadFFmpeg(pct => setP('compress', pct, `Compression... ${pct}%`, ''));

        setP('compress', 0, 'Compression en cours...', '');

        const inputName  = 'cinput.'  + inputExt;
        const outputName = 'coutput.' + outFormat;
        const args = buildCompressArgs(outFormat, isAudio);

        const outputData = await ffRun(inputName, currentCompressFile, outputName, args);
        const blob    = new Blob([outputData.buffer], { type: getMimeType(outFormat) });
        const blobUrl = URL.createObjectURL(blob);
        const dlName  = currentCompressFile.name.replace(/\.[^/.]+$/, '') + '_compressed.' + outFormat;

        document.getElementById('compress-result').innerHTML = resultHTML(dlName, blobUrl, currentCompressFile.size, blob.size);
        document.getElementById('compress-result').classList.remove('hidden');
        setP('compress', 100, 'Terminé !', '');
        pfill.classList.add('done');

    } catch (err) {
        console.error('compress failed:', err);
        setP('compress', 0, 'Erreur : ' + err.message, 'Ouvrez la console (F12) pour plus de détails.');
        pfill.classList.add('error');
    }
}

function buildCompressArgs(outFormat, isAudio) {
    const args    = [];
    const audioBr = document.getElementById('compress-audio-br').value;

    if (!isAudio) {
        const presetVal   = document.getElementById('compress-preset').value;
        const crfMap      = { light: '20', medium: '26', heavy: '32' };
        const crf         = presetVal === 'custom' ? document.getElementById('compress-crf').value : (crfMap[presetVal] || '26');
        const presetSpeed = presetVal === 'light' ? 'slow' : (presetVal === 'heavy' ? 'fast' : 'medium');

        args.push('-c:v', 'libx264', '-crf', crf, '-preset', presetSpeed);

        if (audioBr === 'copy') args.push('-c:a', 'copy');
        else args.push('-c:a', 'aac', '-b:a', audioBr);

        if (outFormat === 'mp4' || outFormat === 'mov') args.push('-movflags', '+faststart');

    } else {
        args.push('-vn');
        if (audioBr === 'copy') {
            args.push('-c:a', 'copy');
        } else {
            const codecMap = { mp3:'libmp3lame', aac:'aac', m4a:'aac', ogg:'libvorbis', opus:'libopus', flac:'flac', wav:'pcm_s16le', aiff:'pcm_s16le' };
            const codec = codecMap[outFormat] || 'libmp3lame';
            const lossless = ['flac','pcm_s16le'];
            args.push('-c:a', codec);
            if (!lossless.includes(codec)) args.push('-b:a', audioBr);
        }
    }

    return args;
}


// =====================================================================
//  PROGRESS HELPERS
// =====================================================================

// setP(tab, pct, text, hint) — tab = 'convert' | 'compress'
function setP(tab, pct, text, hint) {
    const fill = document.getElementById(`${tab}-progress-fill`);
    const txt  = document.getElementById(`${tab}-progress-text`);
    const hnt  = document.getElementById(`${tab}-progress-hint`);
    if (fill) fill.style.width = Math.min(100, pct) + '%';
    if (txt)  txt.textContent  = text;
    if (hnt)  hnt.textContent  = hint;
}


// =====================================================================
//  UTILITIES
// =====================================================================

function showStatus(id, type, msg) {
    const el = document.getElementById(id);
    el.className = 'status ' + type;
    el.textContent = msg;
    el.classList.remove('hidden');
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

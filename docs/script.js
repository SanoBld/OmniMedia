// script.js - MediaTools
// youtube downloader (cobalt API) + file converter + compressor (ffmpeg.wasm 0.11.x)
// nothing runs on a server — it's all browser-side

'use strict';

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
//  VERROU DE PAGE — empêche de fermer/naviguer pendant une opération
// =====================================================================

// Compteur d'opérations actives (téléchargement, conversion, compression)
// Quand > 0, le navigateur affiche une confirmation avant de quitter
let _activeOps = 0;

function opStart() {
    _activeOps++;
    if (_activeOps === 1) {
        window.addEventListener('beforeunload', _beforeUnloadHandler);
    }
}

function opEnd() {
    _activeOps = Math.max(0, _activeOps - 1);
    if (_activeOps === 0) {
        window.removeEventListener('beforeunload', _beforeUnloadHandler);
    }
}

function _beforeUnloadHandler(e) {
    e.preventDefault();
    e.returnValue = 'Une opération est en cours. Quitter maintenant annulera le traitement. Continuer ?';
    return e.returnValue;
}


// =====================================================================
//  TÉLÉCHARGER — cobalt API
// =====================================================================

// Registre communautaire des instances — mis à jour en continu
const COBALT_INSTANCES_REGISTRY = 'https://instances.cobalt.best/api/instances.json';

// Liste élargie d'instances codées en dur — tentées dans l'ordre
// Note : api.cobalt.tools est en dernier car il nécessite une clé Bearer depuis fin 2024
const COBALT_HARDCODED_INSTANCES = [
    'https://cobalt.imput.net',
    'https://cob.freetards.xyz',
    'https://cobalt.synzr.space',
    'https://api.v0.overapi.com/cobalt',
    'https://api.cobalt.tools',
];

// Proxy CORS de secours absolu (fonctionne depuis file:// et origines bloquées)
const CORS_PROXY = 'https://corsproxy.io/?url=';

// Codes HTTP qui signalent un blocage → passer directement à l'instance suivante
const ROTATABLE_HTTP_CODES = new Set([403, 429, 500, 502, 503, 504]);

// Cache d'instances pour éviter de re-fetcher le registre à chaque download
let _cobaltInstancesCache = null;

async function getCobaltInstances() {
    if (_cobaltInstancesCache) return _cobaltInstancesCache;

    try {
        const res = await fetch(COBALT_INSTANCES_REGISTRY, {
            signal: AbortSignal.timeout(7000),
        });
        if (!res.ok) throw new Error(`registry HTTP ${res.status}`);
        const data = await res.json();

        const fromRegistry = Array.isArray(data)
            ? data
                .filter(i => i.cors === 1 && (i.score == null || i.score > 70) && i.api)
                .sort((a, b) => (b.score || 0) - (a.score || 0))
                .map(i => i.api.replace(/\/$/, ''))
                .slice(0, 8)
            : [];

        if (fromRegistry.length > 0) {
            // Fusionner : instances du registre d'abord, puis hardcodées non déjà présentes
            const merged = [...fromRegistry];
            for (const inst of COBALT_HARDCODED_INSTANCES) {
                if (!merged.includes(inst)) merged.push(inst);
            }
            _cobaltInstancesCache = merged;
            console.log('[cobalt] instances fusionnées :', _cobaltInstancesCache);
        } else {
            _cobaltInstancesCache = COBALT_HARDCODED_INSTANCES;
        }
    } catch (err) {
        console.warn('[cobalt] registre inaccessible :', err.message);
        _cobaltInstancesCache = COBALT_HARDCODED_INSTANCES;
    }

    return _cobaltInstancesCache;
}

// ── Listeners UI ─────────────────────────────────────────────────────

document.getElementById('yt-mode').addEventListener('change', function () {
    const audioOnly = this.value === 'audio';
    document.getElementById('yt-vq-wrap').style.display = audioOnly ? 'none' : '';
    document.getElementById('yt-vc-wrap').style.display = audioOnly ? 'none' : '';
});

document.getElementById('yt-af').addEventListener('change', function () {
    const isLossless = ['wav', 'flac'].includes(this.value);
    const wrap = document.getElementById('yt-ab-wrap');
    wrap.style.opacity       = isLossless ? '0.35' : '';
    wrap.style.pointerEvents = isLossless ? 'none'  : '';
});

function ytOpenInCobalt() {
    const url = document.getElementById('yt-url').value.trim();
    window.open(url ? 'https://cobalt.tools/#' + encodeURIComponent(url) : 'https://cobalt.tools', '_blank');
}

// ── Fonction principale de téléchargement ────────────────────────────

async function ytDownload() {
    const url = document.getElementById('yt-url').value.trim();
    if (!url) {
        showStatus('yt-status', 'error', '⚠️ Collez une URL d\'abord.');
        return;
    }

    const mode = document.getElementById('yt-mode').value;
    const mute = document.getElementById('yt-mute-audio').checked;

    // Paramètres Cobalt avec valeurs par défaut garanties (h264 / 720p / mp3)
    const payload = {
        url,
        vCodec:        document.getElementById('yt-vcodec')?.value  || 'h264',
        videoQuality:  document.getElementById('yt-vq')?.value      || '720',
        aFormat:       document.getElementById('yt-af')?.value      || 'mp3',
        audioBitrate:  document.getElementById('yt-ab')?.value      || '128',
        filenameStyle: document.getElementById('yt-filename')?.value || 'pretty',
        downloadMode:  mode === 'audio' ? 'audio' : (mode === 'mute' || mute ? 'mute' : 'auto'),
    };

    console.log('[cobalt] payload :', payload);

    opStart();
    setYtButtons(true);
    showStatus('yt-status', 'info', '🔍 Récupération des instances cobalt...');

    try {
        const instances = await getCobaltInstances();
        let lastError   = null;

        // ── Étape 1 : rotation sur toutes les instances ──────────────
        for (let i = 0; i < instances.length; i++) {
            showStatus('yt-status', 'info',
                `⏳ Instance ${i + 1}/${instances.length} — ${instances[i]}...`);
            try {
                const ok = await tryCobaltInstance(instances[i], payload);
                if (ok) return;
            } catch (err) {
                lastError = err;
                console.warn(`[cobalt] ${instances[i]} →`, err.message);
                // Tous les types d'erreurs (CORS, 403, 429, 5xx, JSON invalide…)
                // → on passe automatiquement à l'instance suivante
            }
        }

        // ── Étape 2 : dernier recours via proxy CORS ─────────────────
        showStatus('yt-status', 'info', '🔄 Tentative via proxy CORS...');
        for (const fallback of COBALT_HARDCODED_INSTANCES.slice(0, 3)) {
            try {
                const proxied = CORS_PROXY + encodeURIComponent(fallback);
                const ok = await tryCobaltInstance(proxied, payload);
                if (ok) return;
            } catch (err) {
                lastError = err;
                console.warn('[cobalt] proxy →', err.message);
            }
        }

        // ── Toutes les instances ont échoué ──────────────────────────
        const isYouTube = url.includes('youtube.com') || url.includes('youtu.be');
        const mainMsg = isYouTube
            ? 'YouTube bloque actuellement les serveurs publics. Veuillez réessayer plus tard ou tester un autre lien.'
            : 'Toutes les instances cobalt ont échoué. Réessayez dans quelques secondes ou essayez un autre lien.';

        showStatus('yt-status', 'error',
            `❌ ${mainMsg}\n\n` +
            `Détail technique : ${lastError?.message || 'aucune instance disponible'}\n` +
            `→ Utilisez "Ouvrir dans Cobalt" pour accéder directement au site.`
        );
    } finally {
        opEnd();
        setYtButtons(false);
    }
}

function setYtButtons(disabled) {
    document.querySelectorAll('#tab-download button').forEach(b => {
        b.disabled      = disabled;
        b.style.opacity = disabled ? '0.55' : '';
        b.style.cursor  = disabled ? 'not-allowed' : '';
    });
}

// ── Tentative sur une instance précise ───────────────────────────────

async function tryCobaltInstance(instanceUrl, payload) {
    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), 15000);

    let res;
    try {
        res = await fetch(instanceUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body:   JSON.stringify(payload),
            signal: controller.signal,
        });
    } catch (err) {
        if (err.name === 'AbortError') throw new Error('timeout (>15s)');
        throw new Error(`réseau/CORS : ${err.message}`);
    } finally {
        clearTimeout(timeoutId);
    }

    if (!res.ok) {
        let errDetail = '';
        try {
            const j = await res.json();
            errDetail = j?.error?.code || j?.text || JSON.stringify(j);
        } catch (_) {}
        const code  = res.status;
        const label = code === 403 ? 'accès refusé' : code === 429 ? 'rate-limited' : 'erreur serveur';
        throw new Error(`HTTP ${code} (${label})${errDetail ? ' : ' + errDetail : ''}`);
    }

    const data = await res.json();
    console.log(`[cobalt] ${instanceUrl} →`, data);

    if (data.status === 'error') {
        throw new Error(`cobalt: ${data.error?.code || JSON.stringify(data.error) || 'unknown'}`);
    }

    if (['redirect', 'tunnel', 'stream'].includes(data.status)) {
        const fname = data.filename || 'download';
        showStatus('yt-status', 'success',
            `✅ Téléchargement de "${fname}" lancé ! Vérifiez vos téléchargements.`);
        triggerDownload(data.url, fname);
        return true;
    }

    if (data.status === 'picker') {
        const items = data.picker || [];
        if (!items.length) throw new Error('picker vide : aucun flux retourné');
        let html = `<strong>${items.length} flux disponibles — cliquez pour télécharger :</strong><br><br>`;
        items.forEach((item, i) => {
            const label = item.type || `Flux ${i + 1}`;
            const thumb = item.thumb
                ? `<img src="${item.thumb}" style="height:36px;vertical-align:middle;margin-right:6px;border-radius:3px">`
                : '';
            html += `${thumb}<a href="${item.url}" target="_blank" rel="noopener" style="color:#60a5fa">${label}</a><br>`;
        });
        const el = document.getElementById('yt-status');
        el.className = 'status info';
        el.innerHTML = html;
        el.classList.remove('hidden');
        return true;
    }

    throw new Error(`statut cobalt inattendu : "${data.status}"`);
}

function triggerDownload(url, filename) {
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.target = '_blank'; a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => document.body.removeChild(a), 600);
}


// =====================================================================
//  FFMPEG 0.11.x — instance partagée (Convert + Compress)
// =====================================================================

let ffmpeg             = null;
let ffLoadPromise      = null;
let ffProgressCallback = null;

// 0 = auto-détection du nombre de threads (recommandé)
const FF_THREADS = '0';

async function loadFFmpeg(onProgress) {
    ffProgressCallback = onProgress || null;

    if (ffmpeg && ffmpeg.isLoaded()) return;

    if (ffLoadPromise) {
        await ffLoadPromise;
        if (!ffmpeg || !ffmpeg.isLoaded()) {
            throw new Error('FFmpeg n\'a pas pu être chargé (rechargez la page).');
        }
        return;
    }

    if (typeof FFmpeg === 'undefined' || typeof FFmpeg.createFFmpeg !== 'function') {
        throw new Error(
            'La librairie FFmpeg.wasm est introuvable. ' +
            'Vérifiez votre connexion et rechargez la page.'
        );
    }

    ffLoadPromise = (async () => {
        const { createFFmpeg } = FFmpeg;
        ffmpeg = createFFmpeg({
            corePath: 'https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.11.0/dist/ffmpeg-core.js',
            log: true,
            progress: ({ ratio }) => {
                const pct = Math.min(99, Math.round(ratio * 100));
                if (typeof ffProgressCallback === 'function') ffProgressCallback(pct);
            },
        });
        await ffmpeg.load();
        console.log('[ffmpeg] 0.11.x chargé ✓');
    })();

    try {
        await ffLoadPromise;
    } catch (err) {
        ffmpeg = null;
        ffLoadPromise = null;
        throw new Error(
            'Échec du chargement de FFmpeg : ' + err.message + '\n' +
            '• La page doit être servie via HTTP (pas file://)\n' +
            '• Vérifiez la console (F12) pour les erreurs réseau/CORS\n' +
            '• Désactivez vos bloqueurs de publicité et réessayez'
        );
    }
}

// Helper standard — write → run (avec threads) → read → unlink
async function ffRun(inputName, inputFile, outputName, args) {
    const { fetchFile } = FFmpeg;
    ffmpeg.FS('writeFile', inputName, await fetchFile(inputFile));
    const cmd = ['-threads', FF_THREADS, '-i', inputName, ...args, outputName];
    console.log('[ffmpeg]', cmd.join(' '));
    await ffmpeg.run(...cmd);
    const data = ffmpeg.FS('readFile', outputName);
    try { ffmpeg.FS('unlink', inputName);  } catch (_) {}
    try { ffmpeg.FS('unlink', outputName); } catch (_) {}
    return data;
}

// Helper avec args AVANT -i (seek rapide pour le trim)
async function ffRunWithInputArgs(inputName, inputFile, outputName, inputArgs, outputArgs) {
    const { fetchFile } = FFmpeg;
    ffmpeg.FS('writeFile', inputName, await fetchFile(inputFile));
    const cmd = [...inputArgs, '-threads', FF_THREADS, '-i', inputName, ...outputArgs, outputName];
    console.log('[ffmpeg]', cmd.join(' '));
    await ffmpeg.run(...cmd);
    const data = ffmpeg.FS('readFile', outputName);
    try { ffmpeg.FS('unlink', inputName);  } catch (_) {}
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
    return {
        mp4:'video/mp4', mkv:'video/x-matroska', webm:'video/webm', avi:'video/x-msvideo',
        mov:'video/quicktime', flv:'video/x-flv', ts:'video/mp2t', gif:'image/gif',
        mp3:'audio/mpeg', aac:'audio/aac', m4a:'audio/mp4', flac:'audio/flac',
        wav:'audio/wav', ogg:'audio/ogg', opus:'audio/opus', aiff:'audio/aiff',
    }[ext] || 'application/octet-stream';
}

function sizeStr(bytes) {
    if (bytes > 1024 ** 3) return (bytes / 1024 ** 3).toFixed(2) + ' GB';
    return (bytes / 1024 ** 2).toFixed(2) + ' MB';
}

function resultHTML(dlName, blobUrl, origBytes, newBytes) {
    const origMB = (origBytes / 1024 ** 2).toFixed(2);
    const newMB  = (newBytes  / 1024 ** 2).toFixed(2);
    const delta  = newBytes < origBytes
        ? `↓ ${((1 - newBytes / origBytes) * 100).toFixed(1)}% plus léger`
        : `↑ ${((newBytes / origBytes - 1) * 100).toFixed(1)}% plus lourd`;
    return `<div class="result-box">
        <p>✅ Terminé ! &nbsp;·&nbsp; <strong>${dlName}</strong><br>
        ${origMB} MB → ${newMB} MB &nbsp;(${delta})</p>
        <a href="${blobUrl}" download="${dlName}" class="btn-primary">↙ Télécharger</a>
    </div>`;
}


// =====================================================================
//  CONVERTIR TAB
// =====================================================================

let currentConvertFile     = null;
let currentConvertFileType = null;

(function setupConvertDrop() {
    const zone  = document.getElementById('convert-drop-zone');
    const input = document.getElementById('convert-file-input');
    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) handleConvertFile(e.dataTransfer.files[0]);
    });
    input.addEventListener('change', e => {
        if (e.target.files[0]) handleConvertFile(e.target.files[0]);
    });
})();

function handleConvertFile(file) {
    currentConvertFile     = file;
    currentConvertFileType = getFileType(file.name);

    document.getElementById('convert-file-info').innerHTML =
        `<strong>${file.name}</strong> &nbsp;·&nbsp; ${sizeStr(file.size)} &nbsp;·&nbsp; type : ${currentConvertFileType}`;

    const fmtSel   = document.getElementById('out-format');
    fmtSel.innerHTML = '';
    OUTPUT_FORMATS[currentConvertFileType].forEach(fmt => {
        const opt = document.createElement('option');
        opt.value = fmt; opt.textContent = fmt.toUpperCase();
        if (fmt === 'mp4' && currentConvertFileType === 'video') opt.selected = true;
        else if (fmt === 'mp3' && currentConvertFileType === 'audio') opt.selected = true;
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
    for (const opt of sel.options) {
        if (opt.value === def) { opt.selected = true; break; }
    }
    onACodecChange();
}

function onACodecChange() {
    const codec    = document.getElementById('a-codec').value;
    const lossless = ['flac','pcm_s16le','pcm_s24le','pcm_s32le','copy'].includes(codec);
    const wrap     = document.getElementById('a-bitrate-wrap');
    wrap.style.opacity       = lossless ? '0.35' : '';
    wrap.style.pointerEvents = lossless ? 'none'  : '';
}

function onVCodecChange() {
    const isCopy = document.getElementById('v-codec').value === 'copy';
    ['crf-wrap', 'preset-wrap'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.style.opacity       = isCopy ? '0.35' : '';
        el.style.pointerEvents = isCopy ? 'none'  : '';
    });
}

function toggleAudioOutputSettings() {
    const fmt        = document.getElementById('out-format').value;
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

    const pfill = document.getElementById('convert-progress-fill');
    document.getElementById('convert-progress-wrap').classList.remove('hidden');
    document.getElementById('convert-result').classList.add('hidden');
    pfill.className = '';
    setFFmpegButtons('convert', true);
    setP('convert', 5, 'Démarrage...', 'Premier chargement de FFmpeg : 10–30s, plus rapide ensuite.');

    opStart();
    try {
        await loadFFmpeg(pct => setP('convert', pct, `Chargement FFmpeg... ${pct}%`, ''));

        setP('convert', 5, 'Lecture du fichier...', '');

        const trimStart  = document.getElementById('trim-start').value.trim();
        const trimEnd    = document.getElementById('trim-end').value.trim();
        const inputArgs  = trimStart ? ['-ss', trimStart] : [];
        const trimArgs   = trimEnd   ? ['-to', trimEnd]   : [];
        const convArgs   = buildFFmpegArgs(outFormat, currentConvertFileType);
        const runArgs    = [...trimArgs, ...convArgs];

        const inputName  = 'input.'  + inputExt;
        const outputName = 'output.' + outFormat;

        setP('convert', 10, 'Conversion en cours...', 'Ne fermez pas cet onglet.');

        const outputData = await ffRunWithInputArgs(inputName, currentConvertFile, outputName, inputArgs, runArgs);
        const blob    = new Blob([outputData.buffer], { type: getMimeType(outFormat) });
        const blobUrl = URL.createObjectURL(blob);
        const dlName  = currentConvertFile.name.replace(/\.[^/.]+$/, '') + '_converted.' + outFormat;

        document.getElementById('convert-result').innerHTML = resultHTML(dlName, blobUrl, currentConvertFile.size, blob.size);
        document.getElementById('convert-result').classList.remove('hidden');
        setP('convert', 100, '✅ Terminé !', '');
        pfill.classList.add('done');

    } catch (err) {
        console.error('[convert]', err);
        setP('convert', 0, '❌ Erreur : ' + err.message, 'Ouvrez la console (F12) pour plus de détails.');
        pfill.classList.add('error');
    } finally {
        opEnd();
        setFFmpegButtons('convert', false);
    }
}

function buildFFmpegArgs(outputFormat, fileType) {
    const args       = [];
    const isAudioOut = ['mp3','aac','m4a','flac','wav','ogg','opus','aiff'].includes(outputFormat);

    if (fileType === 'video' && !isAudioOut) {
        const vCodec      = document.getElementById('v-codec').value;
        const preset      = document.getElementById('v-preset').value;
        const crf         = document.getElementById('v-crf').value;
        const vBitrate    = parseInt(document.getElementById('v-bitrate').value) || 0;
        const vMaxrate    = parseInt(document.getElementById('v-maxrate').value) || 0;
        const res         = document.getElementById('v-res').value;
        const fps         = document.getElementById('v-fps').value;
        const pixFmt      = document.getElementById('v-pixel').value;
        const stripAudio  = document.getElementById('v-strip-audio').value;
        const deinterlace = document.getElementById('v-deinterlace').checked;

        if (vCodec === 'copy') {
            args.push('-c:v', 'copy');
        } else {
            args.push('-c:v', vCodec);
            if (vCodec === 'libvpx-vp9') {
                const vp9map = {
                    ultrafast:'realtime', superfast:'realtime', veryfast:'realtime',
                    faster:'good', fast:'good', medium:'good',
                    slow:'best', slower:'best', veryslow:'best',
                };
                // VITESSE VP9 : cpu-used=4 réduit le temps d'encodage d'environ 50%
                args.push('-deadline', vp9map[preset] || 'good', '-cpu-used', '4');
                if (vBitrate > 0) args.push('-b:v', vBitrate + 'k');
                else args.push('-crf', crf, '-b:v', '0');
            } else {
                // VITESSE H.264/H.265 : -tune fastdecode réduit la charge CPU à la lecture
                args.push('-preset', preset, '-tune', 'fastdecode');
                if (vBitrate > 0) {
                    args.push('-b:v', vBitrate + 'k');
                    if (vMaxrate > 0) args.push('-maxrate', vMaxrate + 'k', '-bufsize', (vMaxrate * 2) + 'k');
                } else {
                    args.push('-crf', crf);
                }
            }
            if (pixFmt) args.push('-pix_fmt', pixFmt);
        }

        const vf = [];
        if (deinterlace) vf.push('yadif=0:-1:0');
        if (res)         vf.push(`scale=${res}:flags=lanczos`);
        if (vf.length)   args.push('-vf', vf.join(','));
        if (fps)         args.push('-r', fps);

        if (stripAudio === 'strip') args.push('-an');
        else args.push(...buildAudioArgs());

    } else {
        args.push('-vn');
        args.push(...buildAudioArgs());
    }

    if (outputFormat === 'mp4' || outputFormat === 'mov') args.push('-movflags', '+faststart');
    if (outputFormat === 'ts')  args.push('-f', 'mpegts');

    if (outputFormat === 'gif') {
        const scale  = document.getElementById('v-res').value || '320:-1';
        const gifFps = document.getElementById('v-fps').value || '15';
        const vfIdx  = args.indexOf('-vf');
        if (vfIdx !== -1) args.splice(vfIdx, 2);
        args.push(
            '-an', '-vf',
            `fps=${gifFps},scale=${scale}:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=bayer`
        );
    }

    return args;
}

function buildAudioArgs() {
    const args      = [];
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
    if (normalize)   af.push('loudnorm=I=-14:LRA=11:TP=-1');
    if (af.length)   args.push('-af', af.join(','));

    return args;
}


// =====================================================================
//  COMPRESSER TAB
// =====================================================================

let currentCompressFile     = null;
let currentCompressFileType = null;

(function setupCompressDrop() {
    const zone  = document.getElementById('compress-drop-zone');
    const input = document.getElementById('compress-file-input');
    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) handleCompressFile(e.dataTransfer.files[0]);
    });
    input.addEventListener('change', e => {
        if (e.target.files[0]) handleCompressFile(e.target.files[0]);
    });
})();

function handleCompressFile(file) {
    currentCompressFile     = file;
    currentCompressFileType = getFileType(file.name);
    const isAudio = currentCompressFileType === 'audio';

    document.getElementById('compress-file-info').innerHTML =
        `<strong>${file.name}</strong> &nbsp;·&nbsp; ${sizeStr(file.size)} &nbsp;·&nbsp; type : ${currentCompressFileType}`;

    document.getElementById('compress-video-section').style.display = isAudio ? 'none' : '';

    const fmtSel   = document.getElementById('compress-format');
    fmtSel.innerHTML = '';
    const inputExt = getExt(file.name);
    const sameOpt  = document.createElement('option');
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
    setFFmpegButtons('compress', true);
    setP('compress', 5, 'Démarrage...', 'Premier chargement de FFmpeg : 10–30s, plus rapide ensuite.');

    opStart();
    try {
        await loadFFmpeg(pct => setP('compress', pct, `Chargement FFmpeg... ${pct}%`, ''));

        setP('compress', 10, 'Compression en cours...', 'Ne fermez pas cet onglet.');

        const inputName  = 'cinput.'  + inputExt;
        const outputName = 'coutput.' + outFormat;
        const args       = buildCompressArgs(outFormat, isAudio);

        const outputData = await ffRun(inputName, currentCompressFile, outputName, args);
        const blob    = new Blob([outputData.buffer], { type: getMimeType(outFormat) });
        const blobUrl = URL.createObjectURL(blob);
        const dlName  = currentCompressFile.name.replace(/\.[^/.]+$/, '') + '_compressed.' + outFormat;

        document.getElementById('compress-result').innerHTML = resultHTML(dlName, blobUrl, currentCompressFile.size, blob.size);
        document.getElementById('compress-result').classList.remove('hidden');
        setP('compress', 100, '✅ Terminé !', '');
        pfill.classList.add('done');

    } catch (err) {
        console.error('[compress]', err);
        setP('compress', 0, '❌ Erreur : ' + err.message, 'Ouvrez la console (F12) pour plus de détails.');
        pfill.classList.add('error');
    } finally {
        opEnd();
        setFFmpegButtons('compress', false);
    }
}

function buildCompressArgs(outFormat, isAudio) {
    const args    = [];
    const audioBr = document.getElementById('compress-audio-br').value;

    if (!isAudio) {
        const presetVal = document.getElementById('compress-preset').value;
        const crfMap    = { light: '20', medium: '26', heavy: '32' };
        const crf       = presetVal === 'custom'
            ? document.getElementById('compress-crf').value
            : (crfMap[presetVal] || '26');

        // VITESSE : preset adapté → light=slow (qualité max), medium=medium, heavy=fast (gain rapide)
        // -tune fastdecode allège le décodage final sans impact visible sur la qualité
        const speedMap = { light: 'slow', medium: 'medium', heavy: 'fast', custom: 'medium' };
        const speed    = speedMap[presetVal] || 'medium';

        args.push('-c:v', 'libx264', '-crf', crf, '-preset', speed, '-tune', 'fastdecode');

        if (audioBr === 'copy') args.push('-c:a', 'copy');
        else args.push('-c:a', 'aac', '-b:a', audioBr);

        if (outFormat === 'mp4' || outFormat === 'mov') args.push('-movflags', '+faststart');

    } else {
        args.push('-vn');
        if (audioBr === 'copy') {
            args.push('-c:a', 'copy');
        } else {
            const codecMap = {
                mp3:'libmp3lame', aac:'aac', m4a:'aac',
                ogg:'libvorbis',  opus:'libopus', flac:'flac',
                wav:'pcm_s16le',  aiff:'pcm_s16le',
            };
            const codec    = codecMap[outFormat] || 'libmp3lame';
            const lossless = ['flac', 'pcm_s16le'];
            args.push('-c:a', codec);
            if (!lossless.includes(codec)) args.push('-b:a', audioBr);
        }
    }

    return args;
}

// Désactive/réactive tous les boutons d'un panneau FFmpeg pendant le traitement
function setFFmpegButtons(tab, disabled) {
    const panelId = tab === 'convert' ? 'tab-convert' : 'tab-compress';
    document.querySelectorAll(`#${panelId} button`).forEach(b => {
        b.disabled      = disabled;
        b.style.opacity = disabled ? '0.55' : '';
        b.style.cursor  = disabled ? 'not-allowed' : '';
    });
}


// =====================================================================
//  PROGRESS HELPERS
// =====================================================================

function setP(tab, pct, text, hint) {
    const fill = document.getElementById(`${tab}-progress-fill`);
    const txt  = document.getElementById(`${tab}-progress-text`);
    const hnt  = document.getElementById(`${tab}-progress-hint`);
    if (fill) fill.style.width = Math.min(100, pct) + '%';
    if (txt)  txt.textContent  = text;
    if (hnt)  hnt.textContent  = hint || '';
}


// =====================================================================
//  UTILITIES
// =====================================================================

function showStatus(id, type, msg) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'status ' + type;
    el.textContent = msg;
    el.classList.remove('hidden');
}

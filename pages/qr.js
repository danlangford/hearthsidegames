const defaultLogoPath = 'flame-deck-compat.svg';
const logoRules = [
    {
        domainIncludes: 'tcg.ravensburgerplay.com',
        logoPath: 'lorcana.svg'
    },
    {
        domainIncludes: 'locator.riftbound.uvsgames.com',
        logoPath: 'riftbound.svg'
    }
];
const gallery = document.getElementById('gallery');
const qrForm = document.getElementById('qrForm');
const qrUrl = document.getElementById('qrUrl');
const qrName = document.getElementById('qrName');

function parseHttpUrl(candidate) {
    try {
        const parsed = new URL(candidate);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
            return parsed;
        }
        return null;
    } catch (err) {
        return null;
    }
}

function normalizeUrl(rawUrl) {
    const trimmed = rawUrl.trim();
    if (!trimmed) {
        return null;
    }

    const direct = parseHttpUrl(trimmed);
    if (direct) {
        return direct.toString();
    }

    const withHttp = parseHttpUrl(`http://${trimmed}`);
    return withHttp ? withHttp.toString() : null;
}

function deriveName(rawName, url) {
    const trimmed = rawName.trim();
    if (trimmed) {
        return trimmed;
    }

    try {
        return new URL(url).hostname;
    } catch (err) {
        return url;
    }
}

function getLogoForUrl(url) {
    try {
        const parsed = new URL(url);
        const host = parsed.hostname.toLowerCase();
        const match = logoRules.find((rule) => host.includes(rule.domainIncludes));
        return match ? match.logoPath : defaultLogoPath;
    } catch (err) {
        // If URL parsing fails, keep default behavior.
        return defaultLogoPath;
    }
}

function addQR(url, name) {
    const template = document.getElementById('tile-template');
    const clone = template.content.cloneNode(true);

    const qrDiv = clone.querySelector('.qr-visual');
    const nameDiv = clone.querySelector('.qr-name');

    // Defensive check (optional but helpful)
    if (!qrDiv || !nameDiv) {
        console.error('Template missing required elements');
        return;
    }

    const logoPath = getLogoForUrl(url);

    const size = 1024;
    const qrCode = new QRCodeStyling({
        width: size,
        height: size,
        data: url,
        image: logoPath,
        imageOptions: {
            crossOrigin: 'anonymous',
            width: Math.floor(size * 0.32),
            height: Math.floor(size * 0.32),
            hideBackgroundDots: true,
            margin: 0
        },
        dotsOptions: {
            color: '#000',
            type: 'rounded'
        },
        backgroundOptions: {
            color: '#fff'
        }
    });

    qrCode.append(qrDiv);
    nameDiv.textContent = name;

    // IMPORTANT: append the fragment, not the tile
    gallery.appendChild(clone);
}


qrForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const normalizedUrl = normalizeUrl(qrUrl.value);
    if (!normalizedUrl) {
        qrUrl.setCustomValidity('Please enter a valid URL');
        qrUrl.reportValidity();
        qrUrl.setCustomValidity('');
        return;
    }

    const name = deriveName(qrName.value, normalizedUrl);
    addQR(normalizedUrl, name);

    qrUrl.value = '';
    qrName.value = '';
    qrUrl.setCustomValidity('');
    qrUrl.focus();
});

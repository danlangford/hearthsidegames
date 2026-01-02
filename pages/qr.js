// Path to logo SVG (white background recommended)
const logoPath = 'flame-deck-compat.svg';
const gallery = document.getElementById('gallery');
const qrForm = document.getElementById('qrForm');
const qrUrl = document.getElementById('qrUrl');
const qrName = document.getElementById('qrName');

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
    const url = qrUrl.value.trim();
    const name = qrName.value.trim();
    if (!url || !name) return;
    addQR(url, name);
    qrUrl.value = '';
    qrName.value = '';
    qrUrl.focus();
});

self.addEventListener('install', (e) => {
    console.log('[Bolos] Service Worker Instalado');
});

self.addEventListener('fetch', (e) => {
    // Vacío (Igual que en Mobatai). 
    // Cumple el requisito de PWA pero deja que el navegador maneje todo normal sin fallar.
});
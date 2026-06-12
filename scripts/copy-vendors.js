const fs = require('fs');
const path = require('path');

// Definimos los archivos a copiar: origen -> destino (rutas relativas a la raíz del proyecto)
const vendorsToCopy = [
  // Chart.js
  {
    src: 'node_modules/chart.js/dist/chart.umd.js',
    dest: 'static/vendors/chart.js/chart.umd.js'
  },
  {
    src: 'node_modules/chart.js/dist/chart.umd.js.map',
    dest: 'static/vendors/chart.js/chart.umd.js.map'
  },
  // Air Datepicker
  {
    src: 'node_modules/air-datepicker/air-datepicker.js',
    dest: 'static/vendors/air-datepicker/air-datepicker.js'
  },
  {
    src: 'node_modules/air-datepicker/air-datepicker.css',
    dest: 'static/vendors/air-datepicker/air-datepicker.css'
  },
  // Bootstrap Icons
  {
    src: 'node_modules/bootstrap-icons/bootstrap-icons.svg',
    dest: 'static/vendors/bootstrap-icons/bootstrap-icons.svg'
  }
];

console.log('Iniciando copia de dependencias a static/vendors/...');

vendorsToCopy.forEach(({ src, dest }) => {
  const srcPath = path.resolve(__dirname, '..', src);
  const destPath = path.resolve(__dirname, '..', dest);

  if (!fs.existsSync(srcPath)) {
    console.error(`✗ Error: No se encontró el archivo de origen en node_modules: ${src}`);
    return;
  }

  // Asegurar que exista la carpeta de destino
  const destDir = path.dirname(destPath);
  if (!fs.existsSync(destDir)) {
    fs.mkdirSync(destDir, { recursive: true });
  }

  // Copiar archivo
  try {
    fs.copyFileSync(srcPath, destPath);
    console.log(`✓ Copiado con éxito: ${src} -> ${dest}`);
  } catch (err) {
    console.error(`✗ Error al copiar ${src}:`, err.message);
  }
});

console.log('Proceso de copia de dependencias finalizado.');

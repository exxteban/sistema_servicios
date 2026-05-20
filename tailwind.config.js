/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: 'class',
    content: [
        "./app/templates/**/*.html",
        "./app/static/js/**/*.js",
        "./control_de_empleados/templates/**/*.html",
        "./gastos_corrientes/templates/**/*.html",
        "./flujo_caja/templates/**/*.html"
    ],
    theme: {
        extend: {
            colors: {
                dark: {
                    bg: '#111827',
                    surface: '#1F2937',
                    border: '#374151',
                    text: '#F3F4F6',
                    muted: '#9CA3AF'
                }
            }
        },
    },
    plugins: [],
}

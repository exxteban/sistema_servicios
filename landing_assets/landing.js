const menuButton = document.querySelector('.menu-toggle')
const mainNav = document.querySelector('.main-nav')
const currentYear = document.querySelector('#current-year')

menuButton?.addEventListener('click', () => {
  const isOpen = menuButton.getAttribute('aria-expanded') === 'true'
  menuButton.setAttribute('aria-expanded', String(!isOpen))
  mainNav?.classList.toggle('open', !isOpen)
})

mainNav?.addEventListener('click', (event) => {
  if (!event.target.closest('a')) return
  menuButton?.setAttribute('aria-expanded', 'false')
  mainNav.classList.remove('open')
})

if (currentYear) currentYear.textContent = String(new Date().getFullYear())

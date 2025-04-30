/**
 * Dark Mode Functionality for Anti-ATS website
 * This script handles theme toggling and persistence across pages
 */

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Create and append the dark mode toggle
    createDarkModeToggle();
    
    // Initialize theme based on user preference
    initializeTheme();
});

/**
 * Creates and appends the dark mode toggle to the navigation bar
 */
function createDarkModeToggle() {
    // Find the navigation bar links container
    const navbarLinks = document.querySelector('.navbar3-links');
    
    if (navbarLinks) {
        // Create the toggle container
        const themeToggle = document.createElement('div');
        themeToggle.className = 'theme-toggle';
        
        // Create the HTML for the toggle
        themeToggle.innerHTML = `
            <span class="toggle-icon dark-icon">🌙</span>
            <span class="toggle-icon light-icon">☀️</span>
            <label class="toggle-switch">
                <input type="checkbox" id="theme-toggle-checkbox">
                <span class="toggle-slider"></span>
            </label>
        `;
        
        // Append the toggle to the navbar
        navbarLinks.appendChild(themeToggle);
        
        // Set up event listener for theme toggle
        const toggleCheckbox = document.getElementById('theme-toggle-checkbox');
        toggleCheckbox.addEventListener('change', function() {
            toggleTheme(this.checked);
        });
    } else {
        console.warn('Navigation bar links container not found. Dark mode toggle could not be added.');
    }
}

/**
 * Initialize theme based on saved preference or system preference
 */
function initializeTheme() {
    const toggleCheckbox = document.getElementById('theme-toggle-checkbox');
    if (!toggleCheckbox) return;
    
    // Check for saved theme preference
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme === 'dark') {
        // Apply dark theme if it was saved
        document.body.classList.remove('light-theme');
        document.body.classList.add('dark-theme');
        toggleCheckbox.checked = true;
    } else if (savedTheme === 'light' || !savedTheme) {
        // Apply light theme if it was saved or no preference
        document.body.classList.add('light-theme');
        document.body.classList.remove('dark-theme');
        toggleCheckbox.checked = false;
    }
    
    // Listen for system preference changes
    const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
    prefersDarkScheme.addEventListener('change', function(e) {
        if (!localStorage.getItem('theme')) {
            // Only apply if user hasn't explicitly chosen a theme
            toggleTheme(e.matches);
        }
    });
}

/**
 * Toggle between light and dark theme
 * @param {boolean} isDark - Whether to switch to dark theme
 */
function toggleTheme(isDark) {
    const body = document.body;
    
    if (isDark) {
        body.classList.remove('light-theme');
        body.classList.add('dark-theme');
        localStorage.setItem('theme', 'dark');
    } else {
        body.classList.add('light-theme');
        body.classList.remove('dark-theme');
        localStorage.setItem('theme', 'light');
    }
}
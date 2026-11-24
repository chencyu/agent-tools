# Copy to start-browser.psd1, which stays local to this machine, to set defaults for start-browser.ps1.
# Each key names a launcher parameter and supplies its value whenever that parameter is omitted.
# Without a Browser key, the launcher uses the system default browser.
@{
    Browser = 'Edge' # or 'Chrome'
}

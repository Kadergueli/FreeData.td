import { getLang, t } from '../i18n.js';

export const TermsView = {
  render() {
    const lang = getLang();
    const citationCode = lang === 'en'
      ? 'Source: [Primary Agency, e.g. INSEED / World Bank] via FreeData.td (https://freedata.td), CC BY 4.0 License.'
      : 'Source : [Organisme Primaire, ex: INSEED / Banque Mondiale] via FreeData.td (https://freedata.td), Licence CC BY 4.0.';

    return `
      <div style="max-width: 860px; margin: 0 auto; padding: 12px 0 40px 0;">
        <div style="border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 30px;">
          <div class="mono-xs text-muted mb-2 uppercase" style="letter-spacing: 0.05em;">
            ${t('terms.badge')} &bull; ${t('terms.last_updated')}
          </div>
          <h1 class="hero-title" style="font-size: 26px; font-weight: 700; color: var(--text); margin: 0 0 8px 0;">
            ${t('terms.title')}
          </h1>
          <p class="mono-sm text-muted" style="margin: 0; line-height: 1.5;">
            ${t('terms.subtitle')}
          </p>
        </div>

        <div class="flex flex-col gap-6" style="color: var(--text);">
          <section>
            <h2 class="mono-md fw-700 mb-2" style="color: var(--cyan); border-bottom: 1px dashed var(--border); padding-bottom: 6px;">
              ${t('terms.sec1_title')}
            </h2>
            <p class="mono-sm text-muted" style="line-height: 1.6; margin: 0;">
              ${t('terms.sec1_text')}
            </p>
          </section>

          <section>
            <h2 class="mono-md fw-700 mb-2" style="color: var(--cyan); border-bottom: 1px dashed var(--border); padding-bottom: 6px;">
              ${t('terms.sec2_title')}
            </h2>
            <p class="mono-sm text-muted mb-3" style="line-height: 1.6; margin: 0 0 12px 0;">
              ${t('terms.sec2_text')}
            </p>
            
            <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border); border-radius: 4px; padding: 12px 16px;">
              <div class="mono-xs text-muted fw-700 mb-1 uppercase" style="letter-spacing: 0.05em;">
                ${t('terms.sec2_example_label')}
              </div>
              <div class="flex justify-between items-center flex-wrap gap-2">
                <code class="mono-sm text-cyan" style="word-break: break-all;" id="citation-code">${citationCode}</code>
                <button class="btn btn-ghost mono-xs flex items-center gap-1" id="copy-citation-btn" style="padding: 4px 10px; border: 1px solid var(--border);">
                  <i data-lucide="copy" style="width:12px;height:12px;"></i> <span id="copy-citation-txt">${t('api.copy')}</span>
                </button>
              </div>
            </div>
          </section>

          <section>
            <h2 class="mono-md fw-700 mb-2" style="color: var(--cyan); border-bottom: 1px dashed var(--border); padding-bottom: 6px;">
              ${t('terms.sec3_title')}
            </h2>
            <p class="mono-sm text-muted" style="line-height: 1.6; margin: 0;">
              ${t('terms.sec3_text')}
            </p>
          </section>

          <section>
            <h2 class="mono-md fw-700 mb-2" style="color: var(--cyan); border-bottom: 1px dashed var(--border); padding-bottom: 6px;">
              ${t('terms.sec4_title')}
            </h2>
            <p class="mono-sm text-muted" style="line-height: 1.6; margin: 0;">
              ${t('terms.sec4_text')}
            </p>
          </section>

          <section>
            <h2 class="mono-md fw-700 mb-2" style="color: var(--cyan); border-bottom: 1px dashed var(--border); padding-bottom: 6px;">
              ${t('terms.sec5_title')}
            </h2>
            <p class="mono-sm text-muted" style="line-height: 1.6; margin: 0;">
              ${t('terms.sec5_text')}
            </p>
          </section>

          <section>
            <h2 class="mono-md fw-700 mb-2" style="color: var(--cyan); border-bottom: 1px dashed var(--border); padding-bottom: 6px;">
              ${t('terms.sec6_title')}
            </h2>
            <p class="mono-sm text-muted" style="line-height: 1.6; margin: 0;">
              ${t('terms.sec6_text')}
            </p>
          </section>
        </div>
      </div>
    `;
  },

  init() {
    if (window.lucide) window.lucide.createIcons();

    const copyBtn = document.getElementById('copy-citation-btn');
    const copyTxt = document.getElementById('copy-citation-txt');
    const citationCode = document.getElementById('citation-code');

    if (copyBtn && citationCode) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(citationCode.textContent.trim()).then(() => {
          if (copyTxt) copyTxt.textContent = t('common.copied');
          setTimeout(() => {
            if (copyTxt) copyTxt.textContent = t('api.copy');
          }, 2000);
        });
      });
    }
  }
};

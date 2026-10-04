/* Shared, dependency-free, keyboard-accessible, scrollable format dropdown. */
(() => {
  'use strict';
  const css = `
.mdm-picker{position:relative;min-width:0;margin:10px 0}
.mdm-picker-toggle{display:flex!important;justify-content:space-between;align-items:center;gap:8px;width:100%;text-align:left;white-space:normal;overflow-wrap:anywhere}
.mdm-picker-list{background:#142031;border:1px solid #3c526d;border-radius:9px;margin-top:5px;max-height:var(--mdm-list-height,240px);overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#70e0c2 #142031;padding:5px}
.mdm-picker-list[hidden]{display:none!important}
.mdm-picker-group{font:700 11px/1.4 system-ui,sans-serif;letter-spacing:.04em;text-transform:uppercase;color:#8ea6c3;padding:11px 8px 6px}
.mdm-picker-option{display:block;width:100%;text-align:left;white-space:normal;overflow-wrap:anywhere;font:13px/1.4 system-ui,sans-serif!important;border:0!important;border-radius:6px!important;background:transparent!important;color:#eaf0fb!important;padding:10px 8px!important;margin:0!important}
.mdm-picker-option:hover,.mdm-picker-option:focus{background:#2b4056!important;outline:2px solid #70e0c2;outline-offset:-2px}
.mdm-picker-option[aria-selected=true]{background:#24453f!important;color:#95f3d8!important}
`;
  let nextId = 0;
  class Picker {
    constructor(onChange = () => {}, onLayout = () => {}) {
      this.onChange = onChange; this.onLayout = onLayout;
      this.items = []; this.value = null; this.options = [];
      this.root = document.createElement('div'); this.root.className = 'mdm-picker';
      this.toggle = document.createElement('button'); this.toggle.type = 'button'; this.toggle.className = 'mdm-picker-toggle';
      this.toggle.setAttribute('aria-label', 'Choose item or playlist, video quality or audio');
      this.toggle.setAttribute('aria-haspopup', 'listbox'); this.toggle.setAttribute('aria-expanded', 'false');
      this.list = document.createElement('div'); this.list.className = 'mdm-picker-list'; this.list.hidden = true;
      this.list.id = 'mdm-format-list-' + (++nextId); this.list.setAttribute('role', 'listbox');
      this.list.setAttribute('aria-label', 'Download options'); this.toggle.setAttribute('aria-controls', this.list.id);
      this.root.append(this.toggle, this.list);
      this.toggle.addEventListener('click', () => this.open(this.list.hidden));
      this.toggle.addEventListener('keydown', e => {
        if (['ArrowDown', 'ArrowUp'].includes(e.key)) { e.preventDefault(); this.open(true, true); }
        if (e.key === 'Escape') this.open(false);
      });
      this.list.addEventListener('keydown', e => {
        const index = this.options.indexOf(e.target);
        let next = index;
        if (e.key === 'ArrowDown') next = Math.min(index + 1, this.options.length - 1);
        else if (e.key === 'ArrowUp') next = Math.max(0, index - 1);
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = this.options.length - 1;
        else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); this.open(false); this.toggle.focus(); return; }
        else return;
        e.preventDefault(); this.options[next]?.focus();
      });
      this.setChoices([]);
    }
    open(show, focus = false) {
      show = !!show && this.items.length > 0;
      this.list.hidden = !show; this.toggle.setAttribute('aria-expanded', String(show));
      if (show && focus) (this.options.find(o => o.dataset.id === this.value?.id) || this.options[0])?.focus();
      this.onLayout();
    }
    setChoices(items) {
      this.items = items; this.value = items[0] || null; this.options = []; this.list.replaceChildren();
      let group = '';
      for (const item of items) {
        if (item.group && item.group !== group) {
          group = item.group;
          const heading = document.createElement('div'); heading.className = 'mdm-picker-group';
          heading.textContent = group; heading.setAttribute('role', 'presentation'); this.list.append(heading);
        }
        const option = document.createElement('button'); option.type = 'button'; option.className = 'mdm-picker-option';
        option.dataset.id = item.id; option.textContent = item.label; option.setAttribute('role', 'option');
        option.addEventListener('click', () => { this.value = item; this.refresh(); this.open(false); this.toggle.focus(); this.onChange(item); });
        this.options.push(option); this.list.append(option);
      }
      this.toggle.disabled = !items.length; this.refresh(); this.open(false);
      this.onChange(this.value);
    }
    refresh() {
      this.toggle.textContent = (this.value?.label || 'Inspect a video to see options') + ' ▾';
      for (const option of this.options) {
        const selected = option.dataset.id === this.value?.id;
        option.setAttribute('aria-selected', String(selected)); option.tabIndex = selected ? 0 : -1;
      }
    }
    get selected() { return this.value; }
  }
  function position(rect, size, viewport) {
    return {
      left:Math.max(viewport.left+8,Math.min(viewport.left+viewport.width-size.width-8,rect.right-size.width-12)),
      top:Math.max(viewport.top+8,Math.min(viewport.top+viewport.height-size.height-8,rect.top+12))
    };
  }
  globalThis.MDMMenu = {Picker, css, position};
})();

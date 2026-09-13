(() => {
  const visible = e => !!e && e.getBoundingClientRect().width > 0 &&
    e.getBoundingClientRect().height > 0 && getComputedStyle(e).visibility !== 'hidden';
  const dialog = [...document.querySelectorAll('[role=dialog]')].find(visible);
  const main = document.querySelector('main');
  const fields = {};
  if (dialog) {
    for (const label of ['3D Technology', 'Material', 'Color', 'Surface Finish', 'Thread', 'Package Box']) {
      const leaf = [...dialog.querySelectorAll('*')].find(e => !e.children.length && e.textContent.trim() === label);
      let group = leaf?.parentElement;
      while (group && group !== dialog && !group.querySelector('button.cur')) group = group.parentElement;
      if (group && group !== dialog) fields[label] = {
        options: [...group.querySelectorAll('button')].map(e => ({label: e.innerText.trim(), disabled: e.disabled})),
        selected: [...group.querySelectorAll('button.cur')].map(e => e.innerText.trim()),
        values: [...group.querySelectorAll('input')].filter(e => visible(e) && e.type !== 'radio')
          .map(e => e.value),
      };
    }
  }
  return {
    url: location.href,
    title: document.title,
    text: main?.innerText || '',
    quantities: [...document.querySelectorAll('main input[role=spinbutton]')]
      .filter(visible).map(e => e.value),
    loading: [...document.querySelectorAll('.el-loading-mask, .is-loading')].some(visible),
    messages: [...document.querySelectorAll('.el-message,.el-form-item__error')]
      .filter(visible).map(e => e.innerText),
    dialog: dialog ? {
      text: dialog.innerText,
      fields,
      selected: [...dialog.querySelectorAll('button.cur')].map(e => e.innerText.trim()),
      inputs: [...dialog.querySelectorAll('input')].filter(visible)
        .map(e => ({placeholder: e.placeholder, role: e.getAttribute('role'), value: e.value})),
    } : null,
  };
})()

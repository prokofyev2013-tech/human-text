/** Рендер результата. Текст создаётся через textContent — без innerHTML из ответа. */

/**
 * @param {HTMLElement} container
 * @param {Array<{title: string, body?: string, bullets?: string[]}>} sections
 */
export function renderSections(container, sections) {
  container.replaceChildren();

  for (const section of sections) {
    if (!section?.title) continue;

    const wrapper = document.createElement("section");
    const heading = document.createElement("h2");
    heading.textContent = section.title;
    wrapper.append(heading);

    if (Array.isArray(section.bullets) && section.bullets.length) {
      const list = document.createElement("ul");
      for (const bullet of section.bullets) {
        const item = document.createElement("li");
        item.textContent = bullet;
        list.append(item);
      }
      wrapper.append(list);
    } else if (section.body) {
      const paragraph = document.createElement("p");
      paragraph.textContent = section.body;
      wrapper.append(paragraph);
    }

    container.append(wrapper);
  }
}

/** Склеивает секции в plain text для буфера обмена. */
export function sectionsToText(sections) {
  return sections
    .map((section) => {
      const lines = [section.title];
      if (section.body) lines.push(section.body);
      if (Array.isArray(section.bullets)) {
        lines.push(...section.bullets.map((bullet) => `— ${bullet}`));
      }
      return lines.join("\n");
    })
    .join("\n\n");
}

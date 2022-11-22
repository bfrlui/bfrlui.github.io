directusImageGet = async () => {
  let html = await (await fetch('view/directusImageGet.html')).text();
  contentEl.innerHTML = html;
}
directusDataGet = async () => {
  let result = await (await fetch('https://802gxr22.directus.app/items/content?filter[app][_eq]=notes')).json();
  let json = JSON.parse(result.data[0].jsonString);
  contentEl.innerHTML = `
    raw data:<br>
    ${JSON.stringify(result.data)}
    <br><br>
    info:<br>
    ${json.data}
  `;
}

let contentEl = document.getElementById('main-content');
console.log('directus module loaded');
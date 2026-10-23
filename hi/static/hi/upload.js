(() => {
    'use strict';
    const t = window.gettext || (x => x), form = document.getElementById('movie-upload');
    if (!form) return;
    const fileInput = document.getElementById('movie-file'), start = document.getElementById('upload-start'),
        pause = document.getElementById('upload-pause'), cancel = document.getElementById('upload-cancel'),
        status = document.getElementById('upload-status'), progress = document.getElementById('upload-progress'),
        result = document.getElementById('upload-result');
    const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
    let session = null, fingerprint = '', running = false, stopped = false, xhr = null, file = null, begun = 0, initialOffset = 0;
    const sessionUrl = () => form.dataset.sessionBase + session.id + '/';
    function message(value, error=false) { status.textContent=value; status.classList.toggle('error',error); }
    function bytes(value) {return (value/1024/1024).toLocaleString(document.documentElement.lang,{maximumFractionDigits:1})+' '+t('МБ');}
    function showProgress(offset) {
        const percent=file?.size?100*offset/file.size:0;progress.value=percent;
        document.getElementById('upload-percent').textContent=percent.toFixed(1)+'% · '+bytes(offset)+' / '+bytes(file?.size||0);
        const seconds=(performance.now()-begun)/1000, rate=seconds>0?(offset-initialOffset)/seconds:0;
        document.getElementById('upload-speed').textContent=running&&rate>0?bytes(rate)+'/'+t('с'):'—';
        const remaining=rate>0?Math.ceil((file.size-offset)/rate):0;
        document.getElementById('upload-eta').textContent=running&&rate>0?t('Осталось:')+' '+Math.floor(remaining/60)+':'+String(remaining%60).padStart(2,'0'):'—';
    }
    function buttons() {start.disabled=running||!file;pause.disabled=!running;cancel.disabled=running||!session||session.state!=='uploading';fileInput.disabled=running;}
    async function api(url, options={}) {
        const response=await fetch(url,{...options,headers:{'X-CSRFToken':csrf,...options.headers}});
        let body;try{body=await response.json();}catch{throw Error(t('Сервер недоступен. Попробуйте продолжить позже.'));}
        if(!response.ok){const e=Error(body.error||t('Ошибка загрузки.'));e.status=response.status;e.data=body;throw e;}return body;
    }
    // SHA-256 also works over plain HTTP in a home LAN, where SubtleCrypto is unavailable.
    function sha256(bytes) {
        const primes=[],K=[],H=[];
        for(let n=2;primes.length<64;n++){if(primes.every(p=>n%p)){primes.push(n);K.push((Math.cbrt(n)%1)*2**32|0);if(H.length<8)H.push((Math.sqrt(n)%1)*2**32|0);}}
        const length=bytes.length,padded=new Uint8Array(Math.ceil((length+9)/64)*64);padded.set(bytes);padded[length]=128;
        const view=new DataView(padded.buffer);view.setUint32(padded.length-4,length*8,false);
        const rot=(x,n)=>(x>>>n)|(x<<(32-n));
        for(let block=0;block<padded.length;block+=64){const w=new Int32Array(64);for(let i=0;i<16;i++)w[i]=view.getInt32(block+i*4,false);
            for(let i=16;i<64;i++){const a=w[i-15],b=w[i-2];w[i]=(w[i-16]+(rot(a,7)^rot(a,18)^(a>>>3))+w[i-7]+(rot(b,17)^rot(b,19)^(b>>>10)))|0;}
            let [a,b,c,d,e,f,g,h]=H;
            for(let i=0;i<64;i++){const t1=(h+(rot(e,6)^rot(e,11)^rot(e,25))+((e&f)^(~e&g))+K[i]+w[i])|0,t2=((rot(a,2)^rot(a,13)^rot(a,22))+((a&b)^(a&c)^(b&c)))|0;h=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;}
            [a,b,c,d,e,f,g,h].forEach((v,i)=>H[i]=(H[i]+v)|0);
        }return H.map(n=>(n>>>0).toString(16).padStart(8,'0')).join('');
    }
    async function identify(selected) {
        const meta=new TextEncoder().encode(JSON.stringify([selected.name,selected.size,selected.lastModified]));
        const first=new Uint8Array(await selected.slice(0,65536).arrayBuffer()),last=new Uint8Array(await selected.slice(Math.max(0,selected.size-65536)).arrayBuffer());
        const bytes=new Uint8Array(meta.length+first.length+last.length);bytes.set(meta);bytes.set(first,meta.length);bytes.set(last,meta.length+first.length);return sha256(bytes);
    }
    function sendChunk(offset,length) {
        return new Promise((resolve,reject)=>{
            const request=new XMLHttpRequest();xhr=request;request.open('PUT',sessionUrl());request.timeout=120000;
            request.setRequestHeader('X-CSRFToken',csrf);request.setRequestHeader('X-Upload-Offset',String(offset));request.setRequestHeader('Content-Type','application/octet-stream');
            request.upload.onprogress=e=>showProgress(offset+e.loaded);
            request.onload=()=>{let data;try{data=JSON.parse(request.responseText);}catch{reject(Error(t('Сервер недоступен. Попробуйте продолжить позже.')));return;}
                if(request.status>=200&&request.status<300)resolve(data);else{const e=Error(data.error||t('Ошибка загрузки.'));e.status=request.status;e.data=data;reject(e);}};
            request.onerror=request.ontimeout=()=>reject(Error(t('Связь прервалась. Нажмите «Продолжить».')));
            request.onabort=()=>reject(Error(t('Загрузка приостановлена.')));
            request.send(file.slice(offset,offset+length));
        }).finally(()=>{xhr=null;});
    }
    const storageKey=()=> 'media-upload:'+fingerprint;
    function remember(){try{localStorage.setItem(storageKey(),session.id);}catch{}}
    async function run() {
        if(running||!file)return;running=true;stopped=false;buttons();message(t('Проверяем файл и свободное место…'));result.hidden=true;
        try{
            fingerprint=await identify(file);
            let previous;try{previous=localStorage.getItem(storageKey());}catch{}
            if(!session&&previous){try{const saved=await api(form.dataset.sessionBase+previous+'/');if(saved.name===file.name&&saved.size===file.size&&saved.state!=='cancelled')session=saved;}catch(e){if(![404,410].includes(e.status))throw e;}}
            if(!session)session=await api(form.dataset.startUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:file.name,size:file.size,fingerprint})});
            remember();begun=performance.now();initialOffset=session.offset;showProgress(session.offset);
            if(session.state==='completed'){complete();return;}
            let retries=0;
            while(session.offset<file.size&&!stopped){
                message(t('Загружаем файл…'));
                try{session=await sendChunk(session.offset,Math.min(session.chunk_size,file.size-session.offset));retries=0;showProgress(session.offset);}
                catch(e){if(stopped)break;if(e.status===409||(!e.status&&retries<3)){retries++;if(retries>3)throw e;message(t('Восстанавливаем соединение…'));await new Promise(r=>setTimeout(r,1000*retries));session=await api(sessionUrl());continue;}throw e;}
            }
            if(stopped){message(t('Загрузка приостановлена.'));return;}
            message(t('Сохраняем публикацию…'));pause.disabled=true;
            const metadata=new FormData(form);metadata.delete('file');session=await api(sessionUrl()+'finish/',{method:'POST',body:metadata});complete();
        }catch(e){message(e.message,true);if(session)showProgress(session.offset);}
        finally{running=false;buttons();if(session?.state==='completed')start.disabled=true;else start.textContent=t('Продолжить');}
    }
    function complete(){message(t('Готово! Файл сохранён.'));showProgress(file.size);result.href=session.post_url||'/dashboard/';result.hidden=false;}
    fileInput.addEventListener('change',()=>{file=fileInput.files[0]||null;session=null;fingerprint='';result.hidden=true;start.textContent=t('Загрузить и сохранить');
        document.getElementById('upload-filename').textContent=file?file.name+' · '+bytes(file.size):'';
        if(file&&file.size>Number(form.dataset.maxBytes)){message(t('Файл превышает лимит 30 ГБ.'),true);file=null;}else{message(t('Готово к загрузке.'));if(file&&!form.elements.title.value)form.elements.title.value=file.name.replace(/\.[^.]+$/,'').slice(0,200);}showProgress(0);buttons();});
    form.addEventListener('submit',e=>{e.preventDefault();if(form.reportValidity())run();});
    pause.addEventListener('click',()=>{stopped=true;xhr?.abort();});
    cancel.addEventListener('click',async()=>{if(!session||running)return;cancel.disabled=true;try{await api(sessionUrl(),{method:'DELETE'});try{localStorage.removeItem(storageKey());}catch{}session=null;progress.value=0;start.textContent=t('Загрузить и сохранить');message(t('Загрузка отменена. Временный файл удалён.'));}catch(e){message(e.message,true);}buttons();});
    buttons();
})();

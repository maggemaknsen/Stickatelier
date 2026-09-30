'use strict';
const form=document.getElementById('loginForm'),password=document.getElementById('password'),button=document.getElementById('loginButton'),error=document.getElementById('loginError');
document.getElementById('showPassword').onchange=e=>{password.type=e.target.checked?'text':'password';};
form.onsubmit=async e=>{
 e.preventDefault();if(button.disabled)return;button.disabled=true;button.textContent='Anmeldung läuft …';error.hidden=true;
 try{
  const response=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-Atelier':'1'},body:JSON.stringify({password:password.value})});
  const result=await response.json();password.value='';
  if(!response.ok)throw new Error(result.error||'Anmeldung fehlgeschlagen.');
  window.location.replace('/');
 }catch(exc){password.value='';error.textContent=exc.message;error.hidden=false;password.focus();}
 finally{button.disabled=false;button.textContent='Anmelden';}
};

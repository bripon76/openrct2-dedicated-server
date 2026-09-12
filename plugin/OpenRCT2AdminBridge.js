/* OpenRCT2 Server OpenRCT2 Admin Bridge
 * Remote plugin, server-side only. Local JSON/TCP bridge + periodic map capture.
 */
const PERMISSIONS = [
  'chat','terraform','set_water_level','toggle_pause','create_ride','remove_ride','build_ride','ride_properties',
  'scenery','path','clear_landscape','guest','staff','park_properties','park_funding','kick_player','modify_groups',
  'set_player_group','cheat','toggle_scenery_cluster','passwordless_login','modify_tile','edit_scenario_options'
];
function result(ok, extra) { return Object.assign({ ok: ok }, extra || {}); }
function captureMap() {
  return result(false, { error:'Headless captureImage is unavailable; use the CLI capture service.' });
}
function status() {
  return {
    ok: true,
    server: { online: network.mode === 'server', version: 'OpenRCT2', park: park.name || 'current park', port: 11753 },
    defaultGroup: network.defaultGroup,
    groups: network.groups.map(g => ({ id: g.id, name: g.name, permissions: g.permissions.slice() })),
    players: network.players.map(p => ({ id:p.id, name:p.name, group:p.group, ping:p.ping, commandsRan:p.commandsRan, moneySpent:p.moneySpent }))
  };
}
function exec(action, args) { return new Promise(resolve => context.executeAction(action, args, r => resolve(r))); }
async function command(q) {
  if (network.mode !== 'server') return result(false,{error:'not running as multiplayer server'});
  switch(q.cmd) {
    case 'status': return status();
    case 'capture_map': return captureMap();
    case 'kick_player': network.kickPlayer(Number(q.playerId)); return result(true);
    case 'set_player_group': { const r=await exec('playersetgroup',{playerId:Number(q.playerId),groupId:Number(q.groupId)}); return result(!r.error,{actionResult:r}); }
    case 'send_message': network.sendMessage(String(q.message || '').slice(0,240)); return result(true);
    case 'add_group': {
      const before=network.groups.map(g=>g.id); network.addGroup(); const g=network.groups.find(x=>!before.includes(x.id));
      if(g&&q.name) g.name=String(q.name).slice(0,64); return result(true,{group:g?{id:g.id,name:g.name}:null});
    }
    case 'remove_group': network.removeGroup(Number(q.groupId)); return result(true);
    case 'set_default_group': network.defaultGroup=Number(q.groupId); return result(true);
    case 'rename_group': { const g=network.getGroup(Number(q.groupId)); if(!g)return result(false,{error:'group not found'}); g.name=String(q.name||'').slice(0,64); return result(true); }
    case 'set_group_permissions': { const g=network.getGroup(Number(q.groupId)); if(!g)return result(false,{error:'group not found'}); g.permissions=(Array.isArray(q.permissions)?q.permissions:[]).filter(p=>PERMISSIONS.includes(p)); return result(true); }
    default: return result(false,{error:'unknown command'});
  }
}
function main() {
  if (network.mode !== 'server') { console.log('[AdminBridge] inactive: not a server'); return; }
  const listener=network.createListener();
  listener.on('connection',sock=>{let buf='';sock.on('data',data=>{buf+=data;let i;while((i=buf.indexOf('\n'))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);if(!line.trim())continue;let q;try{q=JSON.parse(line)}catch(e){sock.write(JSON.stringify(result(false,{error:'invalid json'}))+'\n');continue}command(q).then(r=>sock.write(JSON.stringify(r)+'\n')).catch(e=>sock.write(JSON.stringify(result(false,{error:String(e)}))+'\n'));}})});
  listener.listen(11754,'127.0.0.1');
  console.log('[AdminBridge] listening on 127.0.0.1:11754; map capture is handled by the CLI service');
}
registerPlugin({name:'OpenRCT2 Server Admin Bridge',version:'0.3.0',authors:['OpenRCT2 Server prototype'],type:'remote',licence:'MIT',targetApiVersion:77,main});

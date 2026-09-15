/* OpenRCT2 Admin Bridge
 * Remote plugin, server-side only. Local JSON/TCP bridge + periodic map capture.
 */
const PERMISSIONS = [
  'chat','terraform','set_water_level','toggle_pause','create_ride','remove_ride','build_ride','ride_properties',
  'scenery','path','clear_landscape','guest','staff','park_properties','park_funding','kick_player','modify_groups',
  'set_player_group','cheat','toggle_scenery_cluster','passwordless_login','modify_tile','edit_scenario_options'
];
const MODERATOR_PERMISSIONS = PERMISSIONS.filter(permission => !['passwordless_login', 'set_player_group'].includes(permission));
const PARK_PROPERTIES = [
  'cash', 'bankLoan', 'maxBankLoan', 'entranceFee', 'suggestedGuestMaximum',
  'guestGenerationProbability', 'guestInitialCash', 'guestInitialHappiness',
  'guestInitialHunger', 'guestInitialThirst', 'landPrice', 'constructionRightsPrice'
];
const PARK_FLAGS = ['open', 'samePriceInPark', 'freeEntry', 'difficultGuestGeneration', 'difficultParkRating'];
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
function result(ok, extra) { return Object.assign({ ok: ok }, extra || {}); }
function supportedProperty(name) {
  return PARK_PROPERTIES.includes(name) && typeof park[name] === 'number';
}
function captureMap() {
  return result(false, { error:'Headless captureImage is unavailable; use the CLI capture service.' });
}
function status() {
  const localPlayer = network.currentPlayer;
  return {
    ok: true,
    server: { online: network.mode === 'server', version: 'OpenRCT2', park: park.name || 'current park', port: 11753 },
    parkStats: {
      cash: park.cash, rating: park.rating, bankLoan: park.bankLoan, maxBankLoan: park.maxBankLoan,
      entranceFee: park.entranceFee, guests: park.guests, suggestedGuestMaximum: park.suggestedGuestMaximum,
      guestGenerationProbability: park.guestGenerationProbability, guestInitialCash: park.guestInitialCash,
      guestInitialHappiness: park.guestInitialHappiness, guestInitialHunger: park.guestInitialHunger,
      guestInitialThirst: park.guestInitialThirst, value: park.value, companyValue: park.companyValue,
      totalRideValueForMoney: park.totalRideValueForMoney, totalAdmissions: park.totalAdmissions,
      totalIncomeFromAdmissions: park.totalIncomeFromAdmissions, landPrice: park.landPrice,
      constructionRightsPrice: park.constructionRightsPrice, parkSize: park.parkSize,
      research: park.research, casualtyPenalty: park.casualtyPenalty,
      awards: park.awards || [], monthlyExpenditureAvailable: typeof park.getMonthlyExpenditure === 'function',
      flags: PARK_FLAGS.reduce((flags, flag) => { try { flags[flag] = park.getFlag(flag); } catch (_) {} return flags; }, {})
    },
    announcements: (park.messages || []).slice(-10).map(message => ({ type: message.type, text: message.text, subject: message.subject })),
    defaultGroup: network.defaultGroup,
    groups: network.groups.map(g => ({ id: g.id, name: g.name, permissions: g.permissions.slice() })),
    players: network.players.filter(p => !localPlayer || p.id !== localPlayer.id).map(p => ({ id:p.id, name:p.name, group:p.group, ping:p.ping, commandsRan:p.commandsRan, moneySpent:p.moneySpent })),
    // OpenRCT2 0.5.5 remote plugins expose these values but reject direct game-state writes.
    parkControls: { readableProperties: PARK_PROPERTIES.filter(supportedProperty), propertyWrites:false, guestGeneration:false, flags:false, awards:false, parkMessages:false, propertyWriteReason:'OpenRCT2 remote plugins do not allow direct game-state writes.' }
  };
}
function exec(action, args) { return new Promise(resolve => context.executeAction(action, args, r => resolve(r))); }
async function ensureModeratorGroup() {
  let group = network.groups.find(item => item.name === 'Moderator') || network.groups.find(item => /^Group #\d+$/.test(item.name));
  if (!group) {
    network.addGroup();
    await delay(500);
    group = network.groups.find(item => item.name === 'Group #' + (network.numGroups - 1));
  }
  if (group) {
    group.name = 'Moderator';
    group.permissions = MODERATOR_PERMISSIONS.slice();
  }
}
async function command(q) {
  if (network.mode !== 'server') return result(false,{error:'not running as multiplayer server'});
  switch(q.cmd) {
    case 'status': return status();
    case 'capture_map': return captureMap();
    case 'kick_player': network.kickPlayer(Number(q.playerId)); return result(true);
    case 'set_player_group': { const r=await exec('playersetgroup',{playerId:Number(q.playerId),groupId:Number(q.groupId)}); return result(!r.error,{actionResult:r}); }
    case 'send_message': network.sendMessage(String(q.message || '').slice(0,240)); return result(true);
    case 'post_park_message': {
      return result(false, { error:'OpenRCT2 remote plugins do not allow park messages' });
    }
    case 'set_park_property': {
      return result(false, { error:'OpenRCT2 remote plugins do not allow direct park-property writes' });
    }
    case 'set_guest_generation': {
      return result(false, { error:'OpenRCT2 remote plugins do not allow guest-generation writes' });
    }
    case 'set_park_flag': {
      return result(false, { error:'OpenRCT2 remote plugins do not allow park-flag writes' });
    }
    case 'clear_awards': {
      return result(false, { error:'OpenRCT2 remote plugins do not allow award changes' });
    }
    case 'grant_award': {
      return result(false, { error:'OpenRCT2 remote plugins do not allow award changes' });
    }
    case 'add_group': {
      const before=network.groups.map(g=>g.id); network.addGroup(); const g=network.groups.find(x=>!before.includes(x.id));
      if(g&&q.name) g.name=String(q.name).slice(0,64); return result(true,{group:g?{id:g.id,name:g.name}:null});
    }
    case 'remove_group': network.removeGroup(Number(q.groupId)); return result(true);
    case 'set_default_group': network.defaultGroup=Number(q.groupId); return result(true);
    case 'rename_group': { const g=network.groups.find(group=>Number(group.id)===Number(q.groupId)); if(!g)return result(false,{error:'group not found'}); g.name=String(q.name||'').slice(0,64); await delay(250); return result(true); }
    case 'set_group_permissions': { const g=network.groups.find(group=>Number(group.id)===Number(q.groupId)); if(!g)return result(false,{error:'group not found'}); g.permissions=(Array.isArray(q.permissions)?q.permissions:[]).filter(p=>PERMISSIONS.includes(p)); await delay(250); return result(true); }
    default: return result(false,{error:'unknown command'});
  }
}
function main() {
  if (network.mode !== 'server') { console.log('[AdminBridge] inactive: not a server'); return; }
  ensureModeratorGroup().catch(error => console.log('[AdminBridge] moderator setup failed: ' + error));
  const listener=network.createListener();
  listener.on('connection',sock=>{let buf='';sock.on('data',data=>{buf+=data;let i;while((i=buf.indexOf('\n'))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);if(!line.trim())continue;let q;try{q=JSON.parse(line)}catch(e){sock.write(JSON.stringify(result(false,{error:'invalid json'}))+'\n');continue}command(q).then(r=>sock.write(JSON.stringify(r)+'\n')).catch(e=>sock.write(JSON.stringify(result(false,{error:String(e)}))+'\n'));}})});
  listener.listen(11754,'127.0.0.1');
  console.log('[AdminBridge] listening on 127.0.0.1:11754; map capture is handled by the CLI service');
}
registerPlugin({name:'OpenRCT2 Admin Bridge',version:'0.4.0',authors:['OpenRCT2 Admin'],type:'remote',licence:'MIT',targetApiVersion:77,main});

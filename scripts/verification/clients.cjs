// Protocol-only clients: no resource-pack rendering or player input simulation.
const mc = require(process.argv[2]);
const port = Number(process.argv[3]);
const clients = process.argv.slice(4).map(username => {
  const client = mc.createClient({host: '127.0.0.1', port, username,
    auth: 'offline', version: '1.20.4'});
  client.on('add_resource_pack', p => client.write('resource_pack_receive', {uuid: p.uuid, result: 1}));
  client.on('position', p => client.write('teleport_confirm', {teleportId: p.teleportId}));
  client.on('login', () => console.log(`READY ${username}`));
  client.on('error', e => { console.error(`${username}: ${e.message}`); process.exitCode = 1; });
  client.on('end', reason => console.log(`END ${username}: ${reason}`));
  return client;
});
process.on('SIGTERM', () => {
  clients.forEach(client => client.end());
  setTimeout(() => process.exit(), 500).unref();
});

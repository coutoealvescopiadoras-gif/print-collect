import ssl
import pg8000.native

ctx = ssl.create_default_context()
conn = pg8000.native.Connection(
    "neondb_owner",
    password="npg_U9JHqTsc3LPu",
    host="ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech",
    database="neondb",
    ssl_context=ctx,
    port=5432,
)

print("=" * 90)
print("PROVA - POR QUE A IMPRESSORA TESTE DO POSTO FALCAO SUMIU?")
print("=" * 90)

print("\n[1] Cliente POSTO FALCAO (id=225 partner_id=5 CEA):")
c = conn.run("SELECT id,name,partner_id,created_at FROM clients WHERE id=225")
for r in c:
    print("  id:", r[0], "name:", r[1], "partner_id (revenda):", r[2], "criado_em:", r[3])

print("\n[2] IMPRESSORAS VINCULADAS AO client_id=225 (POSTO FALCAO) HOJE:")
p = conn.run(
    "SELECT id,client_id,ip_address,model,created_at,last_seen "
    "FROM printers WHERE client_id=225 ORDER BY id ASC"
)
print(f"  >>> QUANTIDADE: {len(p)} impressoras.")
if len(p) == 0:
    print("  >>> NÃO TEM NENHUMA IMPRESSORA CADASTRADA NO POSTO FALCAO AINDA (é o esperado!).")
for r in p:
    print("  id:", r[0], "ip:", r[2], "modelo:", r[3], "criada:", r[4], "visto:", r[5])

print("\n[3] IMPRESSORA id=1 (RICOH 192.168.15.220) - DONA ORIGINAL (cliente CEA id=1):")
p1 = conn.run(
    "SELECT p.id,p.client_id,c.name as cliente_nome,p.ip_address,p.model,p.created_at "
    "FROM printers p LEFT JOIN clients c ON c.id=p.client_id WHERE p.id=1"
)
for r in p1:
    print("  id:", r[0], "cliente_id:", r[1], "CLIENTE DONO:", r[2], "ip:", r[3], "modelo:", r[4])

print("\n" + "=" * 90)
print("MOTIVO DO SUMIÇO:")
print("=" * 90)
print("  Mais cedo hoje, nós criamos uma impressora TESTE printer_id=167 com ip 192.168.15.220")
print("  na mão no banco vinculada a client_id=225 (Posto Falcão).")
print("  DEPOIS VOCÊ DISSE QUE ESSA IMPRESSORA 192.168.15.220 NÃO ERA DO POSTO FALCÃO!")
print("  VOCÊ DISSE: 'Essa RICOH é impressora DE TESTE DA CEA COPIADORAS (cliente id=1) há tempos!'")
print("")
print("  Então a pedido seu, eu RODEI DELETE SQL para apagar ela e os readings dela de teste:")
print("  -> DELETE FROM readings WHERE printer_id IN (SELECT id FROM printers WHERE client_id=225)")
print("  -> DELETE FROM alerts    WHERE printer_id IN (SELECT id FROM printers WHERE client_id=225)")
print("  -> DELETE FROM printers  WHERE client_id=225")
print("")
print("  >>> POR ISSO ELA SUMIU! NÓS APAGAMOS DE PROPÓSITO, VOCÊ PEDIU! 🤣")
print("  >>> A impressora REAL do Posto Falcão (a que está LÁ na rede deles) vai ser")
print("      criada automaticamente AMANHÃ quando você rodar o Wizard LWFTASJN num PC")
print("      LÁ na rede do Posto Falcão, NÃO AQUI na rede da Julio/CEA!")
print("=" * 90)

conn.close()

"""
Migração em lote de senhas em texto puro para hash bcrypt.

Não é mais obrigatório rodar este script: o login() e o
verify_channel_password() do app.py/studio.py agora fazem "self-heal"
sozinhos -- na primeira vez que alguém loga (ou confirma a senha do
canal) com uma senha ainda em texto puro, ela já é re-salva como hash
bcrypt automaticamente, sem precisar de nenhum passo manual.

Esse script serve só pra contas/canais que NUNCA mais logam ou mudam a
senha (e por isso nunca passariam pelo self-heal) -- rodar ele garante
que não fique nenhuma senha em texto puro esquecida no banco.

Uso:
    python migrate_passwords.py

Antes era baseado em flask_bcrypt e só olhava a tabela users com um
caminho fixo do Windows (D:\\sqlite\\app.db). Agora usa bcrypt puro
(mesma lib do auth_server.py e do app.py) e também migra channels.password.
"""
import os
import sqlite3
import bcrypt

# Mesmo caminho que app.py/studio.py usam (ver SQLITE_DB em app.py).
if os.name == 'nt':
    SQLITE_DB = r'D:\sqlite\app.db'
else:
    SQLITE_DB = os.path.join(os.path.dirname(__file__), 'app.db')


def _parece_hash_bcrypt(valor):
    if not valor or not isinstance(valor, str):
        return False
    return valor.startswith('$2a$') or valor.startswith('$2b$') or valor.startswith('$2y$')


def hash_password(senha_pura):
    return bcrypt.hashpw(senha_pura.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def migrar_tabela(conn, tabela, coluna_chave):
    c = conn.cursor()
    c.execute(f"SELECT {coluna_chave}, password FROM {tabela}")
    linhas = c.fetchall()
    migrados = 0
    for chave, senha in linhas:
        if senha and not _parece_hash_bcrypt(senha):
            novo_hash = hash_password(senha)
            c.execute(f"UPDATE {tabela} SET password = ? WHERE {coluna_chave} = ?", (novo_hash, chave))
            print(f"[{tabela}] {chave}: senha migrada para hash bcrypt.")
            migrados += 1
    conn.commit()
    return migrados


def main():
    if not os.path.exists(SQLITE_DB):
        print(f"Banco não encontrado em {SQLITE_DB} -- nada a migrar.")
        return

    conn = sqlite3.connect(SQLITE_DB)
    total = 0
    total += migrar_tabela(conn, 'users', 'username')
    total += migrar_tabela(conn, 'channels', 'username')
    conn.close()

    if total == 0:
        print("Nenhuma senha em texto puro encontrada -- banco já estava migrado.")
    else:
        print(f"Migração concluída! {total} senha(s) atualizada(s) para bcrypt.")


if __name__ == '__main__':
    main()

# Import the supplied local SQLite dossier into the NEW Supabase project.
# Set DATABASE_URL in the environment before running. Never commit it or share it.
import json, os, sqlite3, sys
from pathlib import Path
import psycopg2

HERE=Path(__file__).resolve().parent
SQLITE_PATH=Path(os.environ.get('DOSSIER_SQLITE', str(HERE/'PW_ClanDossier.sqlite3')))
DATABASE_URL=os.environ.get('DATABASE_URL','').strip()
if not DATABASE_URL:
    sys.exit('Missing DATABASE_URL. Set it to the NEW Supabase project\'s PostgreSQL connection string.')
if not SQLITE_PATH.exists():
    sys.exit(f'SQLite file not found: {SQLITE_PATH}')

schema=(HERE/'schema_supabase.sql').read_text(encoding='utf-8')
src=sqlite3.connect(str(SQLITE_PATH)); src.row_factory=sqlite3.Row
dst=psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=15)
try:
    with dst:
        with dst.cursor() as cur:
            cur.execute(schema)
            # This importer is intended for the brand-new, dedicated project only.
            cur.execute('TRUNCATE public.equipment, public.stats, public.scans, public.players, public.app_settings, public.item_metadata RESTART IDENTITY CASCADE')
            for table, columns in [
                ('players',['wid','name','class_id','class_name','level','rebirth','first_seen','last_seen']),
                ('scans',['id','wid','name','captured_at','equipment_ok','detailed_ok','error','status_state','status_count','status_ids_json','status_records_json','status_checked_at']),
                ('stats',['scan_id','json','damage_rating','hp_rating','max_hp','max_mp','phys_min','phys_max','phys_def','attack_level','defense_level','critical']),
                ('equipment',['scan_id','slot','template_id','runtime_class','item_count','flags','refine','durability','max_durability','sockets_json','properties_json']),
            ]:
                rows=src.execute(f'SELECT {",".join(columns)} FROM {table}').fetchall()
                if rows:
                    placeholders=','.join(['%s']*len(columns))
                    sql=f'INSERT INTO public.{table} ({",".join(columns)}) VALUES ({placeholders})'
                    cur.executemany(sql,[tuple(r[c] for c in columns) for r in rows])
                print(f'{table}: imported {len(rows)} rows')
            # Advance identity sequence after explicit scan IDs were restored.
            cur.execute("SELECT setval(pg_get_serial_sequence('public.scans','id'), COALESCE((SELECT MAX(id) FROM public.scans),1), true)")
            # Import persistent default scan selection if the old local file exists.
            defaults=HERE/'scan_defaults.json'
            if defaults.exists():
                val=json.loads(defaults.read_text(encoding='utf-8'))
                cur.execute('INSERT INTO public.app_settings(key,value_json) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_at=now()',('scan_defaults',json.dumps(val,ensure_ascii=False)))
            # Import the optional metadata cache, if present in the original folder.
            metadata=HERE/'cache'/'pwdb_items.json'
            if metadata.exists():
                val=json.loads(metadata.read_text(encoding='utf-8'))
                for item_id, meta in val.items():
                    cur.execute('INSERT INTO public.item_metadata(item_id,metadata_json) VALUES(%s,%s) ON CONFLICT(item_id) DO UPDATE SET metadata_json=EXCLUDED.metadata_json,updated_at=now()', (str(item_id),json.dumps(meta,ensure_ascii=False)))
                print(f'item_metadata: imported {len(val)} cached entries')
    print('Migration completed successfully.')
finally:
    src.close(); dst.close()

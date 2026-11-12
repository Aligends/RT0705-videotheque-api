// Parcours de bout en bout du site dans un navigateur (Chromium piloté par Playwright).
//
// Le scénario joue un visiteur, un nouveau membre et l'administrateur : inscription
// validée, film, avis, prêt, compte, export, import, modération, journal, puis les
// redirections refusées et l'affichage sur un écran de téléphone. Il vérifie aussi
// que la console du navigateur ne signale aucune violation de la politique de
// sécurité du contenu.
//
// Il s'attend à une base neuve chargée avec les données de démonstration et
// aux inscriptions en mode « validation » (réglages par défaut) :
//     docker compose down -v && docker compose up -d --build
//
// Prérequis : Node.js et Playwright (npm install playwright && npx playwright install chromium).
// Usage : node tests/navigateur/parcours.js <URL du site> <mot de passe admin> <dossier des captures> [--https]
// Exemple : node tests/navigateur/parcours.js http://localhost:8080 "$(sed -n 's/^ADMIN_MOT_DE_PASSE=//p' .env)" /tmp/captures
// Avec --https, le certificat de l'autorité interne est accepté.
const { chromium } = require('playwright');
const fs = require('fs');

const B = process.argv[2] || 'http://localhost:8080';
const MDP_ADMIN = process.argv[3];
const OUT = process.argv[4] || '.';
const HTTPS = process.argv.includes('--https');
const ADMIN = 'admin@videotheque.local';
const MDP = 'phrase-de-passe-alice';
const MDP2 = 'nouvelle-phrase-alice';

let echecs = 0;
function verifier(nom, condition, detail) {
  if (condition) { console.log('OK    ' + nom); }
  else { echecs++; console.log('ECHEC ' + nom + (detail !== undefined ? ' -> ' + JSON.stringify(detail) : '')); }
}

(async () => {
  const navigateur = await chromium.launch();
  const contexte = await navigateur.newContext({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 2, ignoreHTTPSErrors: HTTPS, acceptDownloads: true });
  const p = await contexte.newPage();
  const consoleErreurs = [];
  // Les réponses 4xx attendues (formulaire refusé, accès interdit) apparaissent dans la console : on ne garde que les autres erreurs.
  p.on('console', m => { if (m.type() === 'error' && !m.text().startsWith('Failed to load resource: the server responded with a status of 4')) consoleErreurs.push(m.text()); });
  p.on('pageerror', e => consoleErreurs.push('pageerror: ' + e.message));
  let confirmations = 0;
  p.on('dialog', d => { confirmations++; d.accept(); });

  const message = async () => (await p.locator('.message').first().innerText()).trim();
  const capture = async nom => p.screenshot({ path: `${OUT}/${nom}.png`, fullPage: true });
  const envoyer = async (selecteur = 'main form.formulaire button.bouton') => { await p.locator(selecteur).first().click(); await p.waitForLoadState(); };
  async function connecter(email, mdp) {
    await p.goto(B + '/connexion');
    await p.fill('[name=email]', email); await p.fill('[name=mot_de_passe]', mdp);
    await envoyer();
  }
  const deconnecter = async () => { await p.locator('header form button').click(); await p.waitForLoadState(); };

  // --- 1. visiteur ---------------------------------------------------
  await p.goto(B + '/');
  verifier('accueil : chiffres clés', (await p.locator('.chiffres b').first().innerText()) === '12');
  await capture('01-accueil');
  await p.goto(B + '/films?q=amelie');
  verifier('recherche sans accent', (await p.locator('.carte strong').allInnerTexts()).join() === "Le Fabuleux Destin d'Amélie Poulain");
  await p.goto(B + '/films/6');
  const fichePublique = await p.locator('main').innerText();
  verifier('visiteur : pas d\'emplacement ni de prêts', !fichePublique.includes('Emplacement') && !fichePublique.includes('Thomas') && !fichePublique.includes('Historique des prêts'));
  verifier('visiteur : aucun bouton de modification', (await p.locator('text=Modifier').count()) === 0);
  await p.goto(B + '/prets');
  verifier('visiteur : /prets renvoie à la connexion', p.url().includes('/connexion?suite=/prets') || p.url().includes('/connexion?suite=%2Fprets'), p.url());
  await p.goto(B + '/admin/journal');
  verifier('visiteur : /admin renvoie à la connexion', p.url().includes('/connexion'));

  // --- 2. inscription : compte en attente ------------------------------
  await p.goto(B + '/inscription');
  await p.fill('[name=nom]', 'Alice'); await p.fill('[name=email]', 'alice@exemple.fr');
  await p.fill('[name=mot_de_passe]', 'azertyuiop'); await p.fill('[name=confirmation]', 'azertyuiop');
  await envoyer();
  verifier('inscription : mot de passe trop courant refusé', (await p.locator('.erreur-champ').innerText()).includes('trop'));
  await p.fill('[name=mot_de_passe]', MDP); await p.fill('[name=confirmation]', 'autre-chose-que-prevu');
  await envoyer();
  verifier('inscription : confirmation différente refusée', (await p.locator('.erreur-champ').innerText()).includes('identiques'));
  await p.fill('[name=mot_de_passe]', MDP); await p.fill('[name=confirmation]', MDP);
  await envoyer();
  verifier('inscription : compte en attente', (await message()).includes('administrateur doit l\'activer'), await message());
  await connecter('alice@exemple.fr', MDP);
  verifier('connexion refusée tant que le compte n\'est pas activé', (await message()).includes('attente de validation'), await message());

  // --- 3. administrateur ---------------------------------------------
  await connecter(ADMIN, 'mauvais-mot-de-passe');
  verifier('mauvais mot de passe refusé', (await message()).includes('incorrect'));
  await connecter(ADMIN, MDP_ADMIN);
  verifier('connexion administrateur', (await message()).includes('Bienvenue'), await message());
  await p.goto(B + '/admin/utilisateurs');
  await capture('05-admin-comptes');
  const ligneAlice = p.locator('tr', { hasText: 'alice@exemple.fr' });
  verifier('compte d\'Alice en attente', (await ligneAlice.innerText()).includes('En attente'));
  await ligneAlice.locator('button[value=activer]').click(); await p.waitForLoadState();
  verifier('activation du compte', (await message()).includes('mis à jour'));
  await deconnecter();
  verifier('déconnexion', (await message()).includes('déconnecté'));

  // --- 4. membre : film, avis ----------------------------------------
  await p.goto(B + '/films/nouveau');
  await p.fill('[name=email]', 'alice@exemple.fr'); await p.fill('[name=mot_de_passe]', MDP); await envoyer();
  verifier('après connexion, retour à la page demandée', p.url().endsWith('/films/nouveau'), p.url());
  await p.fill('[name=titre]', 'Le Samouraï'); await p.fill('[name=annee]', '1967');
  await p.fill('[name=realisateur]', 'Jean-Pierre Melville'); await p.fill('[name=duree_min]', '105');
  await p.selectOption('[name=support]', 'physique'); await p.fill('[name=format]', 'Blu-ray');
  await p.fill('[name=emplacement]', 'Étagère C3');
  await p.check('input[value=Policier]'); await p.fill('[name=nouveaux_genres]', 'Film noir');
  await p.fill('[name=synopsis]', 'Un tueur à gages solitaire est trahi par ses commanditaires.');
  await envoyer();
  verifier('film ajouté', (await message()).includes('a été ajouté'), await message());
  const urlFilm = p.url();
  await p.locator('text=Modifier').first().click(); await p.waitForLoadState();
  await p.fill('[name=titre]', 'Le Samouraï <script>alert(1)</script>'); await envoyer();
  verifier('titre contenant du HTML : affiché tel quel, pas interprété', (await p.locator('h1').innerText()).includes('<script>alert(1)</script>') && (await p.locator('h1 script').count()) === 0);
  await p.locator('text=Modifier').first().click(); await p.waitForLoadState();
  await p.fill('[name=titre]', 'Le Samouraï'); await envoyer();

  await p.selectOption('#avis [name=note]', '9');
  await p.fill('#avis [name=commentaire]', 'Mise en scène glaciale et parfaite.\nÀ voir absolument.');
  await envoyer('#avis form.formulaire button.bouton');
  verifier('avis enregistré', (await message()).includes('avis est enregistré'));
  const fiche = await p.locator('main').innerText();
  verifier('fiche : note moyenne, avis, emplacement visibles', fiche.includes('9 / 10') && fiche.includes('Mise en scène glaciale') && fiche.includes('Étagère C3'));
  await capture('02-fiche-film');
  await p.goto(B + '/films?vu=true');
  verifier('filtre « vus par moi »', (await p.locator('.carte strong').allInnerTexts()).join() === 'Le Samouraï');
  await p.goto(B + '/films?mes_ajouts=true&vu=false');
  verifier('filtres combinés', (await p.locator('.carte').count()) === 0);
  await p.goto(B + '/films');
  await capture('03-films');

  // --- 5. droits du membre ---------------------------------------------
  await p.goto(B + '/films/1');
  verifier('film d\'un autre : pas de bouton Modifier ni Supprimer', (await p.locator('.fiche .actions >> text=Modifier').count()) === 0 && (await p.locator('.fiche .actions >> text=Supprimer').count()) === 0);
  await p.goto(B + '/films/1/modifier'); await p.fill('[name=titre]', 'Piraté'); await envoyer();
  verifier('modifier le film d\'un autre : refusé (403)', (await p.locator('h1').innerText()) === 'Erreur 403');
  const admin403 = await p.goto(B + '/admin/utilisateurs');
  verifier('membre : pages d\'administration refusées (403)', admin403.status() === 403);
  verifier('membre : pas de liens d\'administration', (await p.locator('header >> text=Journal').count()) === 0);

  // --- 6. prêt et retour ---------------------------------------------
  await p.goto(urlFilm);
  await p.locator('a', { hasText: 'Prêter' }).click(); await p.waitForLoadState();
  await p.fill('[name=emprunteur]', 'Zoé'); await p.fill('[name=date_pret]', '2026-11-01'); await p.fill('[name=date_retour_prevue]', '2026-10-01');
  await envoyer();
  verifier('prêt : dates incohérentes refusées', (await p.locator('.erreur-champ').innerText()).includes('précéder'));
  await p.fill('[name=date_retour_prevue]', '2026-11-05'); await envoyer();
  verifier('prêt enregistré', (await message()).includes('est prêté à Zoé'));
  await p.goto(B + '/prets');
  verifier('liste des prêts en cours', (await p.locator('tbody tr').count()) === 3);
  await capture('04-prets');
  await p.locator('tr', { hasText: 'Samouraï' }).locator('button').click(); await p.waitForLoadState();
  verifier('retour enregistré', (await message()).includes('Retour de'));

  // --- 7. compte : nom, mot de passe, export ---------------------------
  await p.goto(B + '/compte');
  await p.fill('form[action$="/compte/nom"] [name=nom]', 'Alice Martin'); await envoyer('form[action$="/compte/nom"] button');
  verifier('nom modifié', (await p.locator('header').innerText()).includes('Alice Martin'));
  await p.fill('[name=ancien]', 'pas-le-bon-mot-de-passe'); await p.fill('[name=nouveau]', MDP2); await p.fill('[name=confirmation]', MDP2);
  await envoyer('form[action$="/compte/mot-de-passe"] button');
  verifier('changement de mot de passe : ancien incorrect refusé', (await p.locator('.erreur-champ').innerText()).includes('incorrect'));
  await p.fill('[name=ancien]', MDP); await p.fill('[name=nouveau]', MDP2); await p.fill('[name=confirmation]', MDP2);
  await envoyer('form[action$="/compte/mot-de-passe"] button');
  verifier('mot de passe modifié, session conservée', (await message()).includes('mot de passe a été modifié') && (await p.locator('header').innerText()).includes('Déconnexion'));
  await capture('06-compte');
  await p.goto(B + '/films');
  const [telechargement] = await Promise.all([p.waitForEvent('download'), p.locator('text=Exporter (JSON)').click()]);
  const cheminExport = `${OUT}/export.json`;
  await telechargement.saveAs(cheminExport);
  const exporte = JSON.parse(fs.readFileSync(cheminExport, 'utf8'));
  verifier('export JSON : 13 films, sans identifiants', exporte.films.length === 13 && !('id' in exporte.films[0]) && exporte.format === 'videotheque-rt0705', exporte.films.length);
  await deconnecter();
  await connecter('alice@exemple.fr', MDP);
  verifier('ancien mot de passe refusé', (await message()).includes('incorrect'));

  // --- 8. administrateur : import, modération, journal -----------------
  await connecter(ADMIN, MDP_ADMIN);
  await p.goto(B + '/admin/import');
  fs.writeFileSync(`${OUT}/invalide.json`, JSON.stringify({ films: [{ titre: '', support: 'betamax' }] }));
  await p.setInputFiles('[name=fichier]', `${OUT}/invalide.json`); await envoyer();
  verifier('import invalide refusé avec le détail', (await p.locator('.message.erreur').innerText()).includes('films[0].titre'));
  fs.writeFileSync(`${OUT}/pasjson.json`, 'ceci n\'est pas du JSON');
  await p.setInputFiles('[name=fichier]', `${OUT}/pasjson.json`); await envoyer();
  verifier('fichier non JSON refusé', (await p.locator('.message.erreur').innerText()).includes('JSON valide'));
  exporte.films.push({ titre: 'Film importé', annee: 2020, support: 'numerique', genres: ['Drame'] });
  fs.writeFileSync(`${OUT}/import.json`, JSON.stringify(exporte));
  await p.setInputFiles('[name=fichier]', `${OUT}/import.json`); await envoyer();
  verifier('import : 1 ajouté, 13 déjà présents', (await p.locator('.message.succes').innerText()).startsWith('1 film importé, 13 déjà présents'), await p.locator('.message').first().innerText());

  await p.goto(urlFilm);
  await p.locator('.avis button', { hasText: 'Supprimer cet avis' }).click(); await p.waitForLoadState();
  verifier('modération : avis supprimé après confirmation', (await message()).includes('avis a été supprimé') && confirmations >= 1);
  await p.goto(B + '/genres');
  await p.fill('[name=nom]', 'film noir'); await envoyer('main form.recherche button');
  verifier('genre en double refusé', (await message()).includes('existe déjà'));
  await p.locator('tr', { hasText: 'Film noir' }).locator('button').click(); await p.waitForLoadState();
  verifier('genre supprimé', (await message()).includes('genre a été supprimé'));
  await p.goto(B + '/prets?tous=1');
  await p.locator('tr', { hasText: 'Samouraï' }).locator('button', { hasText: 'Supprimer' }).click(); await p.waitForLoadState();
  verifier('prêt retiré de l\'historique', (await message()).includes('retiré'));
  await p.goto(urlFilm);
  await p.locator('.fiche .actions button', { hasText: 'Supprimer' }).click(); await p.waitForLoadState();
  verifier('film supprimé par l\'administrateur', (await message()).includes('film a été supprimé'));

  await p.goto(B + '/admin/journal');
  const journal = await p.locator('tbody').innerText();
  verifier('journal : actions tracées', ['Film supprimé', 'Import', 'Échec de connexion', 'Compte modifié', 'Inscription', 'Mot de passe modifié'].every(t => journal.includes(t)));
  await capture('07-admin-journal');
  await p.goto(B + '/admin/journal?action=connexion_echec');
  verifier('journal filtré : les 2 échecs de connexion', (await p.locator('tbody tr').count()) === 2, await p.locator('tbody tr').count());
  await p.goto(B + '/admin/utilisateurs');
  await p.locator('tr', { hasText: 'alice@exemple.fr' }).locator('button', { hasText: 'Supprimer' }).click(); await p.waitForLoadState();
  verifier('compte supprimé', (await message()).includes('compte a été supprimé'));

  // --- 9. redirection après connexion ----------------------------------
  await deconnecter();
  for (const cible of ['https://exemple.org/', '//exemple.org/', '/\\exemple.org/']) {
    await p.goto(B + '/connexion?suite=' + encodeURIComponent(cible));
    await p.fill('[name=email]', ADMIN); await p.fill('[name=mot_de_passe]', MDP_ADMIN); await envoyer();
    verifier('redirection externe refusée : ' + cible, new URL(p.url()).origin === new URL(B).origin && new URL(p.url()).pathname === '/', p.url());
    await deconnecter();
  }

  // --- 10. pages du TP, mobile, console --------------------------------
  const tp = await p.goto(B + '/tp/videotheque');
  if (tp.status() === 200) {
    verifier('page TP : gabarit alimenté par le fichier JSON', (await p.locator('tbody tr').count()) === 4);
    await capture('08-tp-json');
    await p.goto(B + '/tp/formulaire'); await p.fill('[name=titre]', 'Alien'); await p.fill('[name=annee]', '1979'); await envoyer();
    verifier('page TP : traitement du formulaire', (await p.locator('main').innerText()).includes('Formulaire valide'));
  } else { console.log('--    pages TP désactivées (attendu hors mode développement) : ' + tp.status()); }

  const mobile = await navigateur.newContext({ viewport: { width: 375, height: 800 }, ignoreHTTPSErrors: HTTPS });
  const m = await mobile.newPage();
  for (const u of ['/', '/films', '/films/1', '/genres', '/connexion', '/inscription']) {
    await m.goto(B + u);
    const largeur = await m.evaluate(() => document.documentElement.scrollWidth);
    verifier('mobile 375 px sans défilement horizontal : ' + u, largeur <= 375, largeur);
  }
  await m.screenshot({ path: `${OUT}/09-mobile.png`, fullPage: true });

  verifier('aucune erreur dans la console (dont violations de la CSP)', consoleErreurs.length === 0, consoleErreurs);
  await navigateur.close();
  console.log(echecs === 0 ? '\nTous les contrôles sont passés.' : `\n${echecs} contrôle(s) en échec.`);
  process.exit(echecs === 0 ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });

# Retrieval failure diagnostics (dev set)

## hybrid+rerank misses, another mode hits

None.

## Every mode misses

### q021 (multi_sheet, attacks) **Known issue**: passage spans a sub-heading boundary -- no chunking config can contain it whole (docs/design.md)
> After someone uploads a profile photo, our flow redirects them back to a 'returnUrl' query param the client sent us. What should we be checking here, thinking about both the redirect and the upload step together?
Expected source: `Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md` > Preventing Unvalidated Redirects and Forwards

- **bm25** [miss]: Unvalidated Redirects and Forwards Cheat Sheet > Dangerous URL Redirects > Dangerous URL Redirect Example 2 (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md), Laravel Cheat Sheet > Unrestricted File Uploads > Do Not Rely On User Input To Dictate Filenames or Path (Laravel_Cheat_Sheet.md), Ruby on Rails Cheat Sheet > Items > Redirects and Forwards (Ruby_on_Rails_Cheat_Sheet.md)
- **vector** [miss]: Unvalidated Redirects and Forwards Cheat Sheet > Preventing Unvalidated Redirects and Forwards > Validating URLs (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md), Unvalidated Redirects and Forwards Cheat Sheet > Dangerous URL Redirects > Dangerous URL Redirect Example 2 (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md), Unvalidated Redirects and Forwards Cheat Sheet > Introduction (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md)
- **hybrid** [miss]: Unvalidated Redirects and Forwards Cheat Sheet > Dangerous URL Redirects > Dangerous URL Redirect Example 2 (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md), Application Logging Vocabulary Cheat Sheet > File Upload [UPLOAD] > upload_stored[filename,from,to] (Logging_Vocabulary_Cheat_Sheet.md), Unvalidated Redirects and Forwards Cheat Sheet > Dangerous URL Redirects > Dangerous URL Redirect Example 1 (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md)
- **hybrid+rerank** [miss]: Laravel Cheat Sheet > Open Redirection (Laravel_Cheat_Sheet.md), Unvalidated Redirects and Forwards Cheat Sheet > Dangerous URL Redirects > Dangerous URL Redirect Example 2 (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md), DotNet Security Cheat Sheet > Authentication and authorization > Redirects (DotNet_Security_Cheat_Sheet.md)
- **hybrid+rerank (ms-marco-MiniLM-L-6-v2)** [miss]: Unvalidated Redirects and Forwards Cheat Sheet > Dangerous URL Redirects > Dangerous URL Redirect Example 2 (Unvalidated_Redirects_and_Forwards_Cheat_Sheet.md), Ruby on Rails Cheat Sheet > Items > Redirects and Forwards (Ruby_on_Rails_Cheat_Sheet.md), DotNet Security Cheat Sheet > Authentication and authorization > Redirects (DotNet_Security_Cheat_Sheet.md)


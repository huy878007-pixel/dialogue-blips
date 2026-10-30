// Compile-only probe against the current installation. Never installed as a mod.
internal sealed class GameApiProbe : IMod
{
    public void Init(ModManifest manifest) { }
    public void OnEnable()
    {
        var writer = DialogUIManager.Instance.clientBubble.typewriter;
        writer.onCharacterVisible.AddListener(OnCharacter);
        writer.onCharacterVisible.RemoveListener(OnCharacter);
        var source = StoreSoundPlayer.Instance.typewriterAudioSource;
        var client = PlayerStore.Instance.currentClientInstance.GetClientBlueprint();
        var identifier = client.identifier;
        var gender = LocGenderHelper.GetClientGender(client);
        var register = LocGenderHelper.GetClientRegister(client);
    }
    public void OnDisable() { }
    static void OnCharacter(char character) { }
}
